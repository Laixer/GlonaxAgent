#!/usr/bin/env python3

import os
import pickle
import logging
import random
import configparser
import argparse
import traceback
import httpx
import psutil
import asyncio
import websockets

from systemd import journal
from aioice import Candidate
from aiortc import RTCPeerConnection, RTCSessionDescription, InvalidStateError
from aiortc.contrib.media import MediaPlayer, MediaRelay

from log import ColorLogHandler
from glonax import client as gclient
from models import GpsTelemetry, GlonaxPeerConnectionParams, RTCIceCandidateParams
from system import System
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCIceCandidate,
)
from aiortc.rtcicetransport import candidate_from_aioice
from aiortc.contrib.media import MediaPlayer, MediaRelay

import jsonrpc

config = configparser.ConfigParser()
logger = logging.getLogger()


INSTANCE: gclient.Instance | None = None

instance_event = asyncio.Event()


async def remote_address():
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get("https://api.ipify.org?format=json")
            response.raise_for_status()
            response_data = response.json()

            logger.info(f"Remote address: {response_data['ip']}")

            with open("remote_address.dat", "w") as f:
                f.write(response_data["ip"])

        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.error(f"Unknown error: {e}")
            os.remove("remote_address.dat")


async def glonax_server():
    global INSTANCE, instance_event

    from machine import MachineService

    logger.info("Starting glonax task")

    path = config["glonax"]["unix_socket"]

    while True:
        try:
            logger.info(f"Connecting to glonax at {path}")

            machine_service = MachineService()
            user_agent = "glonax-agent/1.0"
            async with await gclient.open_session(
                path, user_agent=user_agent
            ) as session:
                logger.info(f"Glonax connected to {path}")
                logger.info(f"Instance ID: {session.instance.id}")
                logger.info(f"Instance model: {session.instance.model}")
                logger.info(f"Instance type: {session.instance.machine_type}")
                logger.info(f"Instance version: {session.instance.version_string}")
                logger.info(f"Instance serial number: {session.instance.serial_number}")

                INSTANCE = session.instance
                instance_event.set()
                machine_service.feed(session.instance)

                logger.debug("Instance event set")

                with open("instance.dat", "wb") as f:
                    pickle.dump(session.instance, f)

                async for message in session:
                    machine_service.feed(message)

        except asyncio.CancelledError:
            logger.info("Glonax task cancelled")
            return
        except ConnectionError as e:
            logger.debug(f"Glonax connection error: {e}")
            logger.error("Glonax is not running")
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")

        logger.info("Reconnecting to glonax...")
        await asyncio.sleep(1)


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


@dispatcher.rpc_call
def glonax_instance() -> gclient.Instance:
    from machine import MachineService

    # TODO: Object of type UUID is not JSON serializable
    machine_service = MachineService()
    return machine_service.instance


@dispatcher.rpc_call
def glonax_engine() -> gclient.Engine | None:
    from machine import MachineService

    machine_service = MachineService()
    return machine_service.last_engine


@dispatcher.rpc_call
def glonax_motion() -> gclient.Motion | None:
    from machine import MachineService

    machine_service = MachineService()
    return machine_service.last_motion


@dispatcher.rpc_call
def glonax_module_status(module: str) -> gclient.ModuleStatus | None:
    from machine import MachineService

    machine_service = MachineService()
    return machine_service.last_module_status(module)


async def websocket():
    global INSTANCE, instance_event

    logger.debug("Waiting for instance event")

    await instance_event.wait()

    logger.info("Starting websocket task")

    base_url = (config["control"]["base_url"]).rstrip("/")
    uri = f"{base_url}/{INSTANCE.id}/ws"

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


async def update_telemetry(client: httpx.AsyncClient):
    global INSTANCE

    from host import HostService

    logger.info("Starting telemetry update task")

    while True:
        try:
            await asyncio.sleep(15)

            telemetry = HostService.get_telemetry(INSTANCE)

            response = await client.post(f"/telemetry_host", json=telemetry.as_dict())
            response.raise_for_status()

            await asyncio.sleep(45)

        except asyncio.CancelledError:
            break
        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")

async def update_gnss(client: httpx.AsyncClient):
    from location import LocationService

    logger.info("Starting GNSS update task")

    location_service = LocationService()

    while True:
        try:
            await asyncio.sleep(20)

            location = location_service.last_location()
            if location is not None:
                logger.info(
                    f"Location: {location.latitude}, {location.longitude}, {location.altitude}, {location.speed}, {location.heading}"
                )

                gps_telemetry = GpsTelemetry(
                    mode=location.fix,
                    lat=location.latitude,
                    lon=location.longitude,
                    alt=location.altitude,
                    speed=location.speed,
                )

                response = await client.post(f"/telemetry_gps", json=gps_telemetry.as_dict())
                response.raise_for_status()

            await asyncio.sleep(40)

        except asyncio.CancelledError:
            break
        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")


async def http_task_group(tg: asyncio.TaskGroup):
    global INSTANCE, instance_event

    logger.debug("Waiting for instance event")

    await instance_event.wait()

    logger.info("Starting GNSS update task")

    auth_token = config["telemetry"]["token"]
    headers = {"Authorization": "Basic " + auth_token}

    base_url = config["telemetry"]["base_url"]
    async with httpx.AsyncClient(
        http2=True, base_url=base_url, headers=headers
    ) as client:
        tg.create_task(update_telemetry(client))
        tg.create_task(update_gnss(client))

        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            logger.info("HTTP task group cancelled")
            return


async def gps_server():
    from gps import client
    from gps.schemas import TPV

    from location import Location, LocationService

    location_service = LocationService()

    while True:
        try:
            async with await client.open() as c:
                async for result in c:
                    if isinstance(result, TPV):
                        l = Location(
                            fix=result.mode > 1,
                            latitude=result.lat,
                            longitude=result.lon,
                            speed=result.speed,
                            altitude=result.alt,
                            heading=result.track,
                        )
                        location_service.feed(l)

        except asyncio.CancelledError:
            logger.info("GPS handler cancelled")
            return
        except ConnectionError as e:
            logger.debug(f"GPS connection error: {e}")
            logger.error("GPS is not running")
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")

        logger.info("Reconnecting to GPS...")
        await asyncio.sleep(1)


async def main():
    global INSTANCE, instance_event, glonax_peer_connection, media_video0

    logger.info("Starting agent")

    try:
        if os.path.exists("instance.dat"):
            try:
                with open("instance.dat", "rb") as f:
                    INSTANCE = pickle.load(f)
                    logger.info(f"Cacheed instance ID: {INSTANCE.id}")
                    logger.info(f"Cacheed instance model: {INSTANCE.model}")
                    logger.info(f"Cacheed instance type: {INSTANCE.machine_type}")
                    logger.info(f"Cacheed instance version: {INSTANCE.version_string}")
                    logger.info(
                        f"Cacheed instance serial number: {INSTANCE.serial_number}"
                    )
                    instance_event.set()

                    logger.debug("Instance event set")
            # TODO: Should be more specific
            except Exception:
                os.remove("instance.dat")

        await remote_address()

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

        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(glonax_server())
            task2 = tg.create_task(gps_server())
            task3 = tg.create_task(websocket())
            task4 = tg.create_task(http_task_group(tg))
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
        "--config", default="config.ini", help="Specify the configuration file to use"
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
