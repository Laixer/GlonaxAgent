#!/usr/bin/env python3

import os
import pickle
import time
import logging
import random
import configparser
import argparse
import httpx
import psutil
import asyncio
import websockets
from systemd import journal
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay

from glonax import client as gclient
from glonax.message import (
    Message,
    ChannelMessageType,
    ModuleStatus,
    RTCSessionDescription,
)
from models import HostConfig, Telemetry
from process import System
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay

import jsonrpc

config = configparser.ConfigParser()
logger = logging.getLogger()


class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[38;21m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33;1m",
        logging.ERROR: "\033[31;1m",
        logging.CRITICAL: "\033[31;1m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord):
        log_color = self.COLORS.get(record.levelno, self.RESET)
        log_fmt = f"%(asctime)s | {log_color}%(levelname)8s{self.RESET} | %(message)s"
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


class MessageChangeDetector:
    def __init__(self):
        self.last_message: Message | None = None
        self.last_message_update = time.time()

    def process_message(self, message: Message) -> bool:
        has_changed = message != self.last_message or (
            (time.time() - self.last_message_update) > 5
        )
        if has_changed:
            self.last_message = message
            self.last_message_update = time.time()
        return has_changed

    def get_last_message(self) -> Message | None:
        return self.last_message


class StatusChangeDetector:
    def __init__(self):
        self.last_status: dict[str, ModuleStatus] = {}
        self.last_status_update: dict[str, int] = {}

    def process_status(self, status: ModuleStatus) -> bool:
        last_update = self.last_status_update.get(status.name, 0)
        has_changed = (
            status != self.last_status.get(status.name)
            or (time.time() - last_update) > 5
        )
        if has_changed:
            self.last_status[status.name] = status
            self.last_status_update[status.name] = time.time()
        return has_changed


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


async def glonax():
    global INSTANCE, instance_event

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

    except asyncio.CancelledError:
        logger.info("Glonax task cancelled")
        return
    except ConnectionError as e:
        logger.debug(f"Glonax connection error: {e}")
        logger.error("Glonax is not running")


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

        self.__webcam = MediaPlayer(
            self.__video_track, format="v4l2", options=self.__av_options
        )

        relay = MediaRelay()
        video = relay.subscribe(self.__webcam.video)

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
                    await self.__glonax_session.writer.write_frame(message)

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
        await self.__peer_connection.setRemoteDescription(offer)
        answer = await self.__peer_connection.createAnswer()
        await self.__peer_connection.setLocalDescription(answer)

        return self.__peer_connection.localDescription

    async def __run_glonax_read(self, channel):
        while True:
            try:
                data = await self.__glonax_session.reader.read_frame()
                channel.send(data)

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


dispatcher = jsonrpc.Dispatcher()


@dispatcher.rpc_call
async def rpc_setup_rtc(sdp: str):
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
def glonax_instance():
    return INSTANCE.model


async def websocket():
    global INSTANCE, instance_event

    logger.debug("Waiting for instance event")

    await instance_event.wait()

    logger.info("Starting websocket task")

    # engine_detector = MessageChangeDetector()
    # motion_detector = MessageChangeDetector()
    # status_detector = StatusChangeDetector()

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

        logger.info("Reconnecting websocket...")
        await asyncio.sleep(1)


async def update_telemetry():
    global INSTANCE, instance_event

    logger.debug("Waiting for instance event")

    await instance_event.wait()

    logger.info("Starting telemetry update task")

    def seconds_elapsed() -> int:
        return round(time.time() - psutil.boot_time())

    server_authkey = config["server"]["authkey"]
    headers = {"Authorization": "Bearer " + server_authkey}

    base_url = config["server"]["base_url"]
    async with httpx.AsyncClient(
        http2=True, base_url=base_url, headers=headers
    ) as client:
        while True:
            try:
                await asyncio.sleep(15)

                telemetry = Telemetry(
                    memory_used=psutil.virtual_memory().percent,
                    disk_used=psutil.disk_usage("/").percent,
                    cpu_freq=psutil.cpu_freq().current,
                    cpu_load=psutil.getloadavg(),
                    uptime=seconds_elapsed(),
                )
                data = telemetry.model_dump()

                response = await client.post(f"/{INSTANCE.id}/telemetry", json=data)
                response.raise_for_status()

                await asyncio.sleep(30)

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

                await asyncio.sleep(15)

            except asyncio.CancelledError:
                break
            except (
                httpx.HTTPStatusError,
                httpx.ConnectTimeout,
                httpx.ConnectError,
            ) as e:
                logger.error(f"HTTP Error: {e}")
            except Exception as e:
                logger.error(f"Unknown error: {e}")


# TODO: This is experimental
async def gps():
    from gps import client
    from gps.schemas import TPV

    HOST = "127.0.0.1"
    PORT = 2947

    while True:
        try:
            async with await client.open(HOST, PORT) as c:
                i = 0
                async for result in c:
                    if isinstance(result, TPV):
                        if i % 30 == 0:
                            logger.info(
                                f"GPS: Mode:{str(result.mode)} LatLong({result.lat}, {result.lon}) Altitude: {result.alt} Speed: {result.speed} Climb: {result.climb}"
                            )
                        i = i + 1

        except asyncio.CancelledError:
            logger.info("GPS handler cancelled")
            return
        except asyncio.IncompleteReadError as e:
            logger.error("GPS disconnected")
            await asyncio.sleep(1)
        except ConnectionError as e:
            logger.debug(f"GPS connection error: {e}")
            logger.error("GPS is not running")
            await asyncio.sleep(1)


async def main():
    global INSTANCE, instance_event

    try:
        if os.path.exists("instance.dat"):
            with open("instance.dat", "rb") as f:
                INSTANCE = pickle.load(f)
                logger.info(f"Cacheed instance ID: {INSTANCE.id}")
                logger.info(f"Cacheed instance model: {INSTANCE.model}")
                logger.info(f"Cacheed instance type: {INSTANCE.machine_type}")
                logger.info(f"Cacheed instance version: {INSTANCE.version_string}")
                logger.info(f"Cacheed instance serial number: {INSTANCE.serial_number}")
                instance_event.set()

                logger.debug("Instance event set")

        await remote_address()

        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(glonax())
            task2 = tg.create_task(gps())
            task3 = tg.create_task(websocket())
            task4 = tg.create_task(update_telemetry())
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
        handler = logging.StreamHandler()
        handler.setFormatter(ColorFormatter())
        logger.addHandler(handler)

    config.read(args.config)

    asyncio.run(main())
