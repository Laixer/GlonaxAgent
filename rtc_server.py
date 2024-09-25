#!/usr/bin/env python3

import os
import time
import logging
import configparser
import argparse
import traceback
import asyncio
import websockets

from systemd import journal
from log import ColorLogHandler
from aioice import Candidate
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCDataChannel,
    InvalidStateError,
)
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
from aiortc.rtcicetransport import candidate_from_aioice
from aiortc.contrib.media import MediaPlayer, MediaRelay

from glonax import client as gclient
from glonax_agent.models import (
    GlonaxPeerConnectionParams,
    RTCIceCandidateParams,
)
import glonax_agent.jsonrpc as jsonrpc

APP_NAME = "glonax-rtc"
UNIX_SOCKET = "/var/run/glonax.sock"

VIDEO_TRACKS = [0]
VIDEO_SIZES = ["1920x1080", "1280x720", "640x480", "320x240"]

config = configparser.ConfigParser()
logger = logging.getLogger()

instance_id = os.getenv("GLONAX_INSTANCE_ID")
auth_secret = os.getenv("AUTH_SECRET")

glonax_peer_connection = None
media_video0 = None
media_relay = MediaRelay()


class GlonaxPeerConnection:
    def __init__(self, socket_path: str, params: GlonaxPeerConnectionParams):
        global media_video0, media_relay

        self._connection_id = params.connection_id

        self._socket_path = socket_path
        self._user_agent = params.user_agent[:32] + f"/{self._connection_id}"

        self._peer_connection = RTCPeerConnection()
        self._glonax_session = None
        self._task = None
        self._task_monitor = None

        if isinstance(media_video0, MediaPlayer):
            video = media_relay.subscribe(media_video0.video, buffered=False)
            self._peer_connection.addTrack(video)
        else:
            logger.error("No video device available")

        @self._peer_connection.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(
                "Connection state is %s" % self._peer_connection.connectionState
            )
            if self._peer_connection.connectionState == "failed":
                await self._peer_connection.close()
            elif self._peer_connection.connectionState == "connected":
                logger.info(f"RTC connection {self._connection_id} established")
            elif self._peer_connection.connectionState == "closed":
                await self._on_disconnect()

        @self._peer_connection.on("datachannel")
        async def on_datachannel(channel: RTCDataChannel):
            if channel.label == "signal":
                if self._task is None and self._glonax_session is None:
                    self._task = asyncio.create_task(self._run_glonax_read(channel))

            @channel.on("message")
            async def on_message(message):
                match channel.label:
                    case "command":
                        frame = gclient.Frame.from_bytes(message[:10])
                        if frame.type == gclient.MessageType.ECHO:
                            channel.send(message)
                        elif self._glonax_session is not None:
                            await self._glonax_session.writer.write_frame(
                                frame, message[10:]
                            )

                    case "rtc":
                        # TODO: Handle RTC (JSON) messages
                        # - switch media source
                        # - switch video size
                        # - switch video frame rate
                        pass

                    case "management":
                        # TODO: Handle management (JSON) messages
                        pass

    @property
    def connection_id(self) -> int:
        return self._connection_id

    async def set_remote_description(self, offer: RTCSessionDescription) -> None:
        await self._peer_connection.setRemoteDescription(offer)

    async def create_answer(self) -> RTCSessionDescription:
        answer = await self._peer_connection.createAnswer()
        await self._peer_connection.setLocalDescription(answer)
        self._task_monitor = asyncio.create_task(self._monitor())
        return self._peer_connection.localDescription

    async def add_ice_candidate(self, candidate: RTCIceCandidate) -> None:
        await self._peer_connection.addIceCandidate(candidate)

    async def _run_glonax_read(self, channel: RTCDataChannel):
        while True:
            try:
                logger.debug("Connecting to glonax at %s", self._socket_path)

                self._glonax_session = await gclient.open_session(
                    self._socket_path, user_agent=self._user_agent
                )
                await self._glonax_session.motion_stop_all()

                instance_bytes = self._glonax_session.instance.to_bytes()
                frame = gclient.Frame(
                    type=gclient.MessageType.INSTANCE,
                    message_length=len(instance_bytes),
                )
                channel.send(frame.to_bytes() + instance_bytes)

                while True:
                    frame, message = await self._glonax_session.reader.read_frame()
                    # TODO: Deduplicate messages
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
                logger.error(f"Glonax error: {e}")
                logger.critical(f"Unknown error: {traceback.format_exc()}")

            logger.info("Reconnecting to glonax...")
            await asyncio.sleep(1)

    async def _monitor(self):
        await asyncio.sleep(60)

        if self._peer_connection.connectionState != "connected":
            logger.info(f"RTC connection {self._connection_id} timed out")
            await self._peer_connection.close()

    async def _on_disconnect(self) -> None:
        global glonax_peer_connection

        try:
            logger.info(f"RTC connection {self._connection_id} disconnecting")

            if self._task_monitor is not None:
                self._task_monitor.cancel()
                self._task_monitor = None
            if self._task is not None:
                self._task.cancel()
                self._task = None
            if self._glonax_session is not None:
                await self._glonax_session.motion_stop_all()
                await self._glonax_session.close()
                self._glonax_session = None

            if self._peer_connection is not None:
                self._peer_connection = None

        except Exception as e:
            logger.error(f"Error stopping peer connection: {e}")
        finally:
            glonax_peer_connection = None
            logger.info(f"RTC connection {self._connection_id} disconnected")

    async def stop(self) -> None:
        if self._peer_connection is not None:
            await self._peer_connection.close()


# TODO: Add roles to the RPC calls
dispatcher = jsonrpc.Dispatcher()


@dispatcher.rpc_call
async def setup_rtc(
    params: GlonaxPeerConnectionParams, offer: RTCSessionDescription
) -> str:
    from passlib.hash import pbkdf2_sha256

    global glonax_peer_connection

    path = config["glonax"]["unix_socket"]

    # Simulate authentication delay
    time.sleep(0.2)

    if not pbkdf2_sha256.verify(params.auth_token, auth_secret):
        time.sleep(2)
        raise jsonrpc.JSONRPCRuntimeError("Invalid authentication token")

    if not params.connection_id:
        raise jsonrpc.JSONRPCRuntimeError("No connection ID")

    if offer.type != "offer":
        raise jsonrpc.JSONRPCRuntimeError("Invalid offer type, expected offer")

    if glonax_peer_connection is not None:
        raise jsonrpc.JSONRPCRuntimeError("RTC connection already established")

    try:
        logger.info(f"Setting up RTC connection {params.connection_id}")

        peer_connection = GlonaxPeerConnection(path, params)

        await peer_connection.set_remote_description(offer)
        answer = await peer_connection.create_answer()

        glonax_peer_connection = peer_connection
        return answer

    except Exception as e:
        logger.error(f"Error setting up RTC connection: {e}")
        raise jsonrpc.JSONRPCRuntimeError("Error setting up RTC connection")


@dispatcher.rpc_call
async def update_rtc(
    params: GlonaxPeerConnectionParams, candidate_inc: RTCIceCandidateParams
) -> str:
    global glonax_peer_connection

    # TODO: Check authentication token

    if not params.connection_id:
        raise jsonrpc.JSONRPCRuntimeError("No connection ID")

    if glonax_peer_connection is None:
        raise jsonrpc.JSONRPCRuntimeError("No RTC connection established")

    if params.connection_id != glonax_peer_connection.connection_id:
        raise jsonrpc.JSONRPCRuntimeError(
            f"Invalid connection ID {params.connection_id}, current connection ID {glonax_peer_connection.connection_id}"
        )

    if not candidate_inc.candidate:
        raise jsonrpc.JSONRPCRuntimeError("No ICE candidate")

    try:
        logger.info(
            f"Updating RTC connection {params.connection_id} with ICE candidate"
        )

        sdp = candidate_inc.candidate.replace("candidate:", "")
        candidate = Candidate.from_sdp(sdp)

        candidate = candidate_from_aioice(candidate)
        candidate.sdpMid = candidate_inc.sdpMid
        candidate.sdpMLineIndex = candidate_inc.sdpMLineIndex

        await glonax_peer_connection.add_ice_candidate(candidate)

    except Exception as e:
        logger.error(f"Error updating RTC connection: {e}")
        raise jsonrpc.JSONRPCRuntimeError("Error updating RTC connection")


@dispatcher.rpc_call
async def disconnect_rtc(params: GlonaxPeerConnectionParams):
    global glonax_peer_connection

    # TODO: Check authentication token

    if not params.connection_id:
        raise jsonrpc.JSONRPCRuntimeError("Invalid connection ID")

    if glonax_peer_connection is None:
        raise jsonrpc.JSONRPCRuntimeError("No RTC connection established")

    if params.connection_id != glonax_peer_connection.connection_id:
        raise jsonrpc.JSONRPCRuntimeError("Invalid connection ID")

    try:
        logger.info("Disconnecting RPC")

        if glonax_peer_connection is not None:
            await glonax_peer_connection.stop()
            glonax_peer_connection = None

    except Exception as e:
        logger.error(f"Error disconnecting RTC connection: {e}")
        raise jsonrpc.JSONRPCRuntimeError("Error disconnecting RTC connection")


# @dispatcher.rpc_call
# async def reboot():
#     if await System.is_sudo():
#         logger.info("Rebooting system")

#         # await glonax_agent._notify("RTC.COMMAND.REBOOT", "Command system reboot")
#         await System.reboot()
#     else:
#         raise jsonrpc.JSONRPCRuntimeError("User does not have sudo privileges")


# @dispatcher.rpc_call
# async def systemctl(operation: str, service: str):
#     global glonax_agent

#     if await System.is_sudo():
#         logger.info(f"Running systemctl {operation} {service}")

#         # await glonax_agent._notify(
#         #     "RTC.COMMAND.SYSTEMCTL", f"Command systemctl {operation} {service}"
#         # )
#         await System.systemctl(operation, service)
#     else:
#         raise jsonrpc.JSONRPCRuntimeError("User does not have sudo privileges")


# @dispatcher.rpc_call
# async def apt(operation: str, package: str):
#     global glonax_agent

#     if await System.is_sudo():
#         logger.info(f"Running apt {operation} {package}")

#         # await glonax_agent._notify(
#         #     "RTC.COMMAND.APT", f"Command apt {operation} {package}"
#         # )
#         await System.apt(operation, package)
#     else:
#         raise jsonrpc.JSONRPCRuntimeError("User does not have sudo privileges")


async def websocket():
    logger.info("Starting websocket task")

    base_url = config["control"]["base_url"].rstrip("/")
    instance_id = config["DEFAULT"]["instance_id"]
    uri = f"{base_url}/{instance_id}/ws"

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
            logger.error(f"Websocket error: {e}")
            # logger.critical(f"Unknown error: {traceback.format_exc()}")

        logger.info("Reconnecting websocket...")
        await asyncio.sleep(1)


async def main():
    # import socketio

    global glonax_peer_connection, media_video0

    logger.info(f"Starting {APP_NAME}")

    try:
        # glonax_agent.media_service.add_source(config["camera0"])

        # TODO: Create a service for the video device
        try:
            camera0 = config["camera0"]
            device = camera0["device"]

            logger.info(f"Opening video device {device}")

            video_size = camera0.get("video_size", "1280x720")
            if video_size not in VIDEO_SIZES:
                raise ValueError("Invalid video size")

            media_video0 = MediaPlayer(
                device,
                format="v4l2",
                options={
                    "framerate": "30",
                    "video_size": video_size,
                    "preset": "ultrafast",
                    "tune": "zerolatency",
                },
            )
        except Exception as e:
            logger.error(f"Error opening video device: {e}")

        # sio = socketio.AsyncClient()

        # @sio.event
        # async def connect():
        #     logger.info("SocketIO connection established")

        # @sio.event
        # async def hello(data):
        #     logger.info("message received with ", data)
        #     await sio.emit("my response", {"response": "my response"})

        # @sio.event
        # async def disconnect():
        #     logger.info("SocketIO disconnected")

        # await sio.connect("http://urchin-app-l3b6h.ondigitalocean.app")
        # # await sio.connect("http://localhost:3000")
        # await sio.wait()

        await websocket()

    except asyncio.CancelledError:
        if glonax_peer_connection is not None:
            await glonax_peer_connection.stop()
        if media_video0 is not None:
            media_video0._stop(media_video0.video)
            media_video0 = None

        logger.info("Agent is gracefully shutting down")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Glonax RTC proxy")
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
    parser.add_argument(
        "-i",
        "--instance",
        default=instance_id,
        help="Specify the instance ID to use",
    )
    parser.add_argument(
        "-s",
        "--socket",
        default=UNIX_SOCKET,
        help="Specify the UNIX socket path to use",
    )
    args = parser.parse_args()

    log_level = logging.getLevelName(args.log_level.upper())
    logger.setLevel(log_level)

    if args.log_systemd:
        logger.addHandler(journal.JournaldLogHandler(identifier=APP_NAME))
    else:
        logger.addHandler(ColorLogHandler())

    if args.instance is None:
        print("Instance ID is required")
        exit(1)

    config.read(args.config)
    config["DEFAULT"]["instance_id"] = args.instance
    config["glonax"]["unix_socket"] = args.socket

    asyncio.run(main())
