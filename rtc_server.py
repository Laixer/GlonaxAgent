#!/usr/bin/env python3

import os
import pickle
import logging
import configparser
import argparse
import traceback
import asyncio
import websockets

from systemd import journal
from aioice import Candidate
from aiortc import RTCPeerConnection, RTCSessionDescription, InvalidStateError
from aiortc.contrib.media import MediaPlayer, MediaRelay

from glonax_agent import GlonaxAgent
from log import ColorLogHandler
from glonax import client as gclient
from glonax_agent.models import (
    GpsTelemetry,
    GlonaxPeerConnectionParams,
    RTCIceCandidateParams,
)
from glonax_agent.system import System
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
)
from glonax_agent.management import ManagementService
from aiortc.rtcicetransport import candidate_from_aioice
from aiortc.contrib.media import MediaPlayer, MediaRelay

import jsonrpc

config = configparser.ConfigParser()
logger = logging.getLogger()


INSTANCE: gclient.Instance | None = None

# instance_event = asyncio.Event()

management_service: ManagementService | None = None

glonax_agent: GlonaxAgent | None = None

glonax_peer_connection = None
media_video0 = None
media_relay = MediaRelay()


class GlonaxPeerConnection:
    allowed_video_tracks = [0]
    allowed_video_sizes = ["1920x1080", "1280x720", "640x480"]

    def __init__(self, socket_path: str, params: GlonaxPeerConnectionParams):
        global media_video0, media_relay

        self._connection_id = params.connection_id

        self.__socket_path = socket_path
        self.__user_agent = params.user_agent

        self.__peer_connection = RTCPeerConnection()
        self.__glonax_session = None
        self.__task = None

        video = media_relay.subscribe(media_video0.video, buffered=False)

        self.__peer_connection.addTrack(video)

        @self.__peer_connection.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(
                "Connection state is %s" % self.__peer_connection.connectionState
            )
            if self.__peer_connection.connectionState == "failed":
                await self.__peer_connection.close()
                await self._stop()
            elif self.__peer_connection.connectionState == "connected":
                logger.info("RTC connection established")
            elif self.__peer_connection.connectionState == "closed":
                await self._stop()

        @self.__peer_connection.on("datachannel")
        async def on_datachannel(channel):
            if channel.label == "signal":
                if self.__task is None and self.__glonax_session is None:
                    self.__task = asyncio.create_task(self.__run_glonax_read(channel))

            @channel.on("message")
            async def on_message(message):
                if channel.label == "command":
                    frame = gclient.Frame.from_bytes(message[:10])
                    if frame.type == gclient.MessageType.ECHO:
                        channel.send(message)
                    elif self.__glonax_session is not None:
                        await self.__glonax_session.writer.write_frame(
                            frame, message[10:]
                        )

    @property
    def connection_id(self) -> int:
        return self._connection_id

    @property
    def user_agent(self) -> str:
        return self.__user_agent

    @property
    def socket_path(self) -> str:
        return self.__socket_path

    @property
    def video_track(self) -> str:
        return self.__video_track

    async def set_remote_description(self, offer: RTCSessionDescription) -> None:
        await self.__peer_connection.setRemoteDescription(offer)

    async def create_answer(self) -> RTCSessionDescription:
        answer = await self.__peer_connection.createAnswer()
        await self.__peer_connection.setLocalDescription(answer)
        return self.__peer_connection.localDescription

    async def add_ice_candidate(self, candidate: RTCIceCandidate) -> None:
        await self.__peer_connection.addIceCandidate(candidate)

    async def __run_glonax_read(self, channel):
        while True:
            try:
                logger.debug("Connecting to glonax at %s", self.__socket_path)

                self.__glonax_session = await gclient.open_session(
                    self.__socket_path, user_agent=self.__user_agent
                )
                await self.__glonax_session.motion_stop_all()

                instance_bytes = self.__glonax_session.instance.to_bytes()
                frame = gclient.Frame(
                    type=gclient.MessageType.INSTANCE,
                    message_length=len(instance_bytes),
                )
                channel.send(frame.to_bytes() + instance_bytes)

                while True:
                    frame, message = await self.__glonax_session.reader.read_frame()
                    channel.send(frame.to_bytes() + message)

            except asyncio.CancelledError:
                logger.info("Glonax task cancelled")
                return
            except InvalidStateError:
                logger.debug("Data channel closed")
                return
            except ConnectionError as e:
                logger.debug(f"Glonax connection error: {e}")
                logger.error("Glonax is not running")
            except Exception as e:
                logger.critical(f"Unknown error: {traceback.format_exc()}")

            logger.info("Reconnecting to glonax...")
            await asyncio.sleep(1)

    async def _stop(self) -> None:
        global glonax_peer_connection

        logger.info("Stopping peer connection")

        if self.__task is not None:
            self.__task.cancel()
            self.__task = None
        if self.__glonax_session is not None:
            await self.__glonax_session.motion_stop_all()
            await self.__glonax_session.close()
            self.__glonax_session = None

        if self.__peer_connection is not None:
            await self.__peer_connection.close()
            self.__peer_connection = None

        glonax_peer_connection = None


# TODO: Add roles to the RPC calls
dispatcher = jsonrpc.Dispatcher()


@dispatcher.rpc_call
async def setup_rtc(
    params: GlonaxPeerConnectionParams, offer: RTCSessionDescription
) -> str:
    global glonax_peer_connection

    path = config["glonax"]["unix_socket"]

    if not params.connection_id:
        raise jsonrpc.JSONRPCRuntimeError("Invalid connection ID")

    if offer.type != "offer":
        raise jsonrpc.JSONRPCRuntimeError("Invalid offer type")

    if glonax_peer_connection is not None:
        raise jsonrpc.JSONRPCRuntimeError("RTC connection already established")

    logger.info(f"Setting up RTC connection {params.connection_id}")

    peer_connection = GlonaxPeerConnection(path, params)

    await peer_connection.set_remote_description(offer)
    answer = await peer_connection.create_answer()

    glonax_peer_connection = peer_connection
    return answer


@dispatcher.rpc_call
async def update_rtc(
    params: GlonaxPeerConnectionParams, candidate_inc: RTCIceCandidateParams
) -> str:
    global glonax_peer_connection

    if not params.connection_id:
        raise jsonrpc.JSONRPCRuntimeError("Invalid connection ID")

    if glonax_peer_connection is None:
        raise jsonrpc.JSONRPCRuntimeError("No RTC connection established")

    if params.connection_id != glonax_peer_connection.connection_id:
        raise jsonrpc.JSONRPCRuntimeError("Invalid connection ID")

    logger.info(f"Updating RTC connection {params.connection_id} with ICE candidate")

    sdp = candidate_inc.candidate.replace("candidate:", "")
    candidate = Candidate.from_sdp(sdp)

    candidate = candidate_from_aioice(candidate)
    candidate.sdpMid = candidate_inc.sdpMid
    candidate.sdpMLineIndex = candidate_inc.sdpMLineIndex

    await glonax_peer_connection.add_ice_candidate(candidate)


@dispatcher.rpc_call
async def disconnect_rtc(params: GlonaxPeerConnectionParams):
    global glonax_peer_connection

    if not params.connection_id:
        raise jsonrpc.JSONRPCRuntimeError("Invalid connection ID")

    if glonax_peer_connection is None:
        raise jsonrpc.JSONRPCRuntimeError("No RTC connection established")

    if params.connection_id != glonax_peer_connection.connection_id:
        raise jsonrpc.JSONRPCRuntimeError("Invalid connection ID")

    logger.info("Disconnecting RPC")

    if glonax_peer_connection is not None:
        await glonax_peer_connection._stop()
        glonax_peer_connection = None


@dispatcher.rpc_call
async def reboot():
    if await System.is_sudo():
        logger.info("Rebooting system")
        await System.reboot()
    else:
        raise jsonrpc.JSONRPCRuntimeError("User does not have sudo privileges")


@dispatcher.rpc_call
async def systemctl(operation: str, service: str):
    # services = ["glonax", "glonax-agent", "glonax-inpput"]
    # if service in services:
    #     proc_service_restart(service_name)
    if await System.is_sudo():
        logger.info(f"Running systemctl {operation} {service}")
        await System.systemctl(operation, service)
    else:
        raise jsonrpc.JSONRPCRuntimeError("User does not have sudo privileges")


@dispatcher.rpc_call
async def apt(operation: str, package: str):
    if await System.is_sudo():
        logger.info(f"Running apt {operation} {package}")
        await System.apt(operation, package)
    else:
        raise jsonrpc.JSONRPCRuntimeError("User does not have sudo privileges")


@dispatcher.rpc_call
def echo(input):
    return input


async def websocket():
    global INSTANCE, glonax_agent

    logger.debug("Waiting for instance event")

    # await instance_event.wait()

    logger.info("Starting websocket task")

    base_url = (config["control"]["base_url"]).rstrip("/")
    uri = f"{base_url}/{glonax_agent.instance.id}/ws"

    while True:
        try:
            logger.info(f"Connecting to websocket at {uri}")

            async with websockets.connect(uri) as websocket:
                logger.info(f"Websocket connected to {uri}")

                while True:
                    message = await websocket.recv()
                    response = await dispatcher(message)
                    if response is not None:
                        await websocket.send(response.json())

        except asyncio.CancelledError:
            logger.info("Websocket reader cancelled")
            return
        except websockets.ConnectionClosed:
            logger.info("Websocket connection closed")
        except TimeoutError:
            logger.error("Websocket connection timed out")
        except ConnectionResetError:
            logger.error("Websocket connection reset")
        except ConnectionRefusedError:
            logger.error("Websocket connection refused")
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")

        logger.info("Reconnecting websocket...")
        await asyncio.sleep(1)


async def main():
    global INSTANCE, glonax_agent, glonax_peer_connection, media_video0

    glonax_agent = GlonaxAgent(config)

    logger.info("Starting agent")

    try:
        await glonax_agent._boot()

        # TODO: Create a service for the video device
        try:
            camera0 = config["camera0"]
            device = camera0["device"]

            logger.info(f"Opening video device {device}")

            media_video0 = MediaPlayer(
                device,
                format="v4l2",
                options={
                    "framerate": camera0.get("frame_rate", "30"),
                    "video_size": camera0.get("video_size", "640x480"),
                    "preset": "ultrafast",
                    "tune": "zerolatency",
                },
            )
        except Exception as e:
            logger.error(f"Error opening video device: {e}")

        await websocket()

    except asyncio.CancelledError:
        if glonax_peer_connection is not None:
            await glonax_peer_connection._stop()
        if media_video0 is not None:
            media_video0._stop(media_video0.video)
            media_video0 = None

        logger.info("Agent is gracefully shutting down")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Glonax agent for the Laixer Edge platform"
    )
    parser.add_argument(
        "-l",
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level",
    )
    parser.add_argument(
        "--log-systemd",
        action="store_true",
        help="Enable logging to systemd journal",
    )
    parser.add_argument(
        "-c",
        "--config",
        default="config.ini",
        help="Specify the configuration file to use",
    )
    args = parser.parse_args()

    log_level = logging.getLevelName(args.log_level.upper())
    logger.setLevel(log_level)

    if args.log_systemd:
        logger.addHandler(journal.JournaldLogHandler(identifier="glonax-agent"))
    else:
        logger.addHandler(ColorLogHandler())

    config.read(args.config)

    asyncio.run(main())
