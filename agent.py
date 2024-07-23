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
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay

from log import ColorLogHandler
from glonax import client as gclient
from models import HostConfig
from system import System
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate
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


async def glonax_server():
    global INSTANCE, instance_event

    from machine import MachineService

    logger.info("Starting glonax task")

    path = config["glonax"]["unix_socket"]

    try:
        logger.info(f"Connecting to glonax at {path}")

        user_agent = "glonax-agent/1.0"
        async with await gclient.open_session(path, user_agent=user_agent) as session:
            logger.info(f"Glonax connected to {path}")
            logger.info(f"Instance ID: {session.instance.id}")
            logger.info(f"Instance model: {session.instance.model}")
            logger.info(f"Instance type: {session.instance.machine_type}")
            logger.info(f"Instance version: {session.instance.version_string}")
            logger.info(f"Instance serial number: {session.instance.serial_number}")

            INSTANCE = session.instance
            instance_event.set()

            logger.debug("Instance event set")

            with open("instance.dat", "wb") as f:
                pickle.dump(session.instance, f)

            machine_service = MachineService()
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


peers = set()


class RTCGlonaxPeerConnection:
    global peers

    def __init__(self, socket_path: str, user_agent: str = "glonax-rtc/1.0"):
        self.__socket_path = socket_path
        self.__user_agent = user_agent

        self.__video_track = "/dev/video0"
        self.__av_options = {
            "framerate": "30",
            # "video_size": "640x480",
            "video_size": "1280x720",
            "preset": "ultrafast",
            "tune": "zerolatency",
        }

        self.__peer_connection = RTCPeerConnection()
        self.__glonax_session = None
        self.__task = None

        # TOOD: Throws av.error.OSError: [Errno 16] Device or resource busy: '/dev/video0'
        self.__webcam = MediaPlayer(
            self.__video_track, format="v4l2", options=self.__av_options
        )

        relay = MediaRelay()
        video = relay.subscribe(self.__webcam.video, buffered=False)

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
                peers.add(self)
            elif self.__peer_connection.connectionState == "closed":
                await self._stop()

        @self.__peer_connection.on("datachannel")
        async def on_datachannel(channel):
            if channel.label == "command":
                if self.__glonax_session is None:
                    await self.__start_glonax()
                if self.__task is None:
                    assert self.__glonax_session is not None
                    self.__task = asyncio.create_task(self.__run_glonax_read(channel))

            @channel.on("message")
            async def on_message(message):
                if channel.label == "command" and self.__glonax_session is not None:
                    frame = gclient.Frame.from_bytes(message[:10])
                    await self.__glonax_session.writer.write_frame(frame, message[10:])

    @property
    def user_agent(self) -> str:
        return self.__user_agent

    @property
    def socket_path(self) -> str:
        return self.__socket_path

    @property
    def video_track(self) -> str:
        return self.__video_track

    async def set_session_description(
        self, offer: RTCSessionDescription
    ) -> RTCSessionDescription:
        # TODO: Throws AttributeError: 'dict' object has no attribute 'splitlines'
        await self.__peer_connection.setRemoteDescription(offer)
        answer = await self.__peer_connection.createAnswer()
        await self.__peer_connection.setLocalDescription(answer)

        return self.__peer_connection.localDescription

    async def __run_glonax_read(self, channel):
        while True:
            try:
                frame, message = await self.__glonax_session.reader.read_frame()
                channel.send(frame.to_bytes() + message)

            except asyncio.CancelledError:
                logger.info("Glonax task cancelled")
                break
            except ConnectionError as e:
                logger.error(f"Glonax connection error: {e}")
                await asyncio.sleep(1)

    async def __start_glonax(self) -> None:
        logger.debug("Open gloanx session to %s", self.__socket_path)

        self.__glonax_session = await gclient.open_session(
            self.__socket_path, user_agent=self.__user_agent
        )
        await self.__glonax_session.motion_stop_all()

    async def _stop(self) -> None:
        logger.info("Stopping peer connection")

        if self.__task is not None:
            self.__task.cancel()
        if self.__glonax_session is not None:
            await self.__glonax_session.motion_stop_all()
            await self.__glonax_session.close()
        # TODO: We should not be calling this
        self.__webcam._stop(self.__webcam.video)
        peers.remove(self)


# TODO: Add roles to the RPC calls
dispatcher = jsonrpc.Dispatcher()


# TODO: Accept and return 'RTCSessionDescription' as a parameter
@dispatcher.rpc_call
async def setup_rtc(sdp: str) -> str:
    path = config["glonax"]["unix_socket"]

    logger.info("Setting up RTC connection")

    # FUTURE: Support multiple RTC connections
    if len(peers) > 0:
        logger.error("RTC connection already established")
        return None

    peer = RTCGlonaxPeerConnection(path)
    offer = RTCSessionDescription(type="offer", sdp=sdp)
    answer = await peer.set_session_description(offer)

    return answer.sdp


@dispatcher.rpc_call
async def update_rtc(candidate: RTCIceCandidate) -> str:
    logger.info("Updating RTC connection with ICE candidate")
    logger.debug(f"ICE candidate: {candidate}")


@dispatcher.rpc_call
async def reboot():
    if await System.is_sudo():
        logger.info("Rebooting system")
        await System.reboot()
    else:
        logger.error("User does not have sudo privileges")


@dispatcher.rpc_call
async def systemctl(operation: str, service: str):
    # services = ["glonax", "glonax-agent", "glonax-inpput"]
    # if service in services:
    #     proc_service_restart(service_name)
    if await System.is_sudo():
        logger.info(f"Running systemctl {operation} {service}")
        await System.systemctl(operation, service)
    else:
        logger.error("User does not have sudo privileges")


@dispatcher.rpc_call
async def apt(operation: str, package: str):
    if await System.is_sudo():
        logger.info(f"Running apt {operation} {package}")
        await System.apt(operation, package)
    else:
        logger.error("User does not have sudo privileges")


@dispatcher.rpc_call
def echo(input):
    return input


@dispatcher.rpc_call
def glonax_instance() -> gclient.Instance:
    return INSTANCE


async def websocket():
    global INSTANCE, instance_event

    logger.debug("Waiting for instance event")

    await instance_event.wait()

    logger.info("Starting websocket task")

    # TODO: Build url from config
    base_url = (
        config["server"]["base_url"]
        .replace("http://", "ws://")
        .replace("https://", "wss://")
        .rstrip("/")
    )
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

            telemetry = HostService.get_telemetry()
            data = telemetry.model_dump()

            response = await client.post(f"/{INSTANCE.id}/telemetry", json=data)
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


async def update_host(client: httpx.AsyncClient):
    global INSTANCE

    logger.info("Starting host update task")

    while True:
        try:
            await asyncio.sleep(15)

            # TODO: Retrieve from HostService
            host_config = HostConfig(
                hostname=os.uname().nodename,
                kernel=os.uname().release,
                memory_total=psutil.virtual_memory().total,
                cpu_count=psutil.cpu_count(),
                model=INSTANCE.model,
                version=INSTANCE.version_string,
                serial_number=INSTANCE.serial_number,
            )
            data = host_config.model_dump()

            if random.randint(1, 25) == 1:
                response = await client.put(f"/{INSTANCE.id}/host", json=data)
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

            # response = await client.post(f"/{INSTANCE.id}/telemetry", json=data)
            # response.raise_for_status()

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

    server_authkey = config["server"]["authkey"]
    headers = {"Authorization": "Bearer " + server_authkey}

    base_url = config["server"]["base_url"]
    async with httpx.AsyncClient(
        http2=True, base_url=base_url, headers=headers
    ) as client:
        tg.create_task(update_telemetry(client))
        tg.create_task(update_host(client))
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

    while True:
        try:
            async with await client.open() as c:
                location_service = LocationService()
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
            await asyncio.sleep(1)
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")


async def main():
    global INSTANCE, instance_event

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
            except Exception:
                os.remove("instance.dat")

        await remote_address()

        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(glonax_server())
            task2 = tg.create_task(gps_server())
            task3 = tg.create_task(websocket())
            task4 = tg.create_task(http_task_group(tg))
    except asyncio.CancelledError:
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
