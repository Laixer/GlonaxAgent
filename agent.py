#!/usr/bin/env python3

import os
import time
import logging
import random
import configparser
import argparse
import httpx
import psutil
import json
import asyncio
import websockets

from glonax import client as gclient
from glonax.client import Session
from glonax.message import (
    Message,
    ChannelMessageType,
    ModuleStatus,
    RTCSessionDescription,
)
from pydantic import ValidationError
from aiochannel import Channel, ChannelClosed, ChannelFull
from models import HostConfig, Telemetry
from process import proc_reboot, proc_service_restart
from systemd import journal

config = configparser.ConfigParser()
logger = logging.getLogger()


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[38;21m",
        "INFO": "\033[32m",
        "WARNING": "\033[33;1m",
        "ERROR": "\033[31;1m",
        "CRITICAL": "\033[31;1m",
    }
    RESET = "\033[0m"

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
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

        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.error(f"Unknown error: {e}")


async def create_webrtc_stream(
    description: RTCSessionDescription, name: str
) -> Message:
    async with httpx.AsyncClient() as client:
        try:
            go2rtc_base_url = "http://localhost:1984/api"
            response = await client.post(
                f"{go2rtc_base_url}/webrtc?src={name}", json=description.model_dump()
            )
            response.raise_for_status()
            response_data = response.json()

            peer = RTCSessionDescription(type="answer", sdp=response_data["sdp"])
            return Message(type=ChannelMessageType.PEER, topic="answer", payload=peer)

        except (
            httpx.HTTPStatusError,
            httpx.ConnectTimeout,
            httpx.ConnectError,
        ) as e:
            logger.error(f"HTTP Error: {e}")
        except Exception as e:
            logger.error(f"Unknown error: {e}")


async def glonax(signal_channel: Channel[Message], command_channel: Channel[Message]):
    global INSTANCE, instance_event

    logger.info("Starting glonax task")

    path = config["glonax"]["unix_socket"]

    while True:
        try:
            logger.info(f"Connecting to glonax at {path}")

            reader, writer = await gclient.open_unix_connection(path)

            # TODO: Wrap in single function
            async with Session(reader, writer) as session:
                await session.handshake()

                logger.info(f"Glonax connected to {path}")
                logger.info(f"Instance ID: {session.instance.id}")
                logger.info(f"Instance model: {session.instance.model}")
                logger.info(f"Instance type: {session.instance.machine_type}")
                logger.info(f"Instance version: {session.instance.version_string}")
                logger.info(f"Instance serial number: {session.instance.serial_number}")

                INSTANCE = session.instance
                instance_event.set()

                logger.debug("Instance event set")

                async def read_command_channel():
                    async for message in command_channel:
                        if message.topic == "control":
                            logger.info("Sending control message")
                            await session.writer.control(message.payload)
                        elif message.topic == "engine":
                            logger.info("Sending engine message")
                            await session.writer.engine(message.payload)
                        elif message.topic == "motion":
                            await session.writer.motion(message.payload)

                async def read_session():
                    while True:
                        try:
                            message = await session.recv_message()
                            if message is not None:
                                signal_channel.put_nowait(message)

                        except ChannelFull:
                            logger.warning("Glonax signal channel is full")

                await asyncio.gather(read_command_channel(), read_session())

        except asyncio.CancelledError:
            logger.info("Glonax task cancelled")
            return
        except ChannelClosed:
            logger.error("Glonax channel closed")
            return
        except asyncio.IncompleteReadError as e:
            logger.error("Glonax disconnected")
        except ConnectionError as e:
            logger.error(f"Glonax connection error: {e}")

        logger.info("Reconnecting glonax...")
        await asyncio.sleep(1)


async def websocket(
    signal_channel: Channel[Message], command_channel: Channel[Message]
):
    global INSTANCE, instance_event

    logger.debug("Waiting for instance event")

    await instance_event.wait()

    logger.info("Starting websocket task")

    engine_detector = MessageChangeDetector()
    status_detector = StatusChangeDetector()

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

                async def read_signal_channel():
                    async for message in signal_channel:
                        if message.topic == "engine":
                            if engine_detector.process_message(message):
                                await websocket.send(message.model_dump_json())
                        elif message.topic == "status":
                            if status_detector.process_status(message.payload):
                                await websocket.send(message.model_dump_json())

                async def read_socket():
                    while True:
                        try:
                            message = await websocket.recv()

                            # TODO: Dont let pydantic determine the payload type
                            message = Message.model_validate_json(message)
                            if message.type == ChannelMessageType.COMMAND:
                                if message.topic == "process":
                                    logger.info("Received process command")
                                    # await proc_reboot()
                                    # await proc_service_restart("glonax")
                                    # TODO: Add process command handler
                                else:
                                    command_channel.put_nowait(message)
                            elif message.type == ChannelMessageType.PEER:
                                if message.topic == "offer":
                                    logger.info("RTC Offer: Creating peer connection")
                                    default_camera = "linux_usbcam"
                                    answer = await create_webrtc_stream(
                                        message.payload, default_camera
                                    )
                                    await websocket.send(answer.model_dump_json())

                        except ChannelFull:
                            logger.warning("Websocket command channel is full")
                        except json.JSONDecodeError:
                            logger.error("Failed to decode JSON message")
                        except ValidationError as e:
                            logger.error(f"Validation error: {e}")

                await asyncio.gather(read_signal_channel(), read_socket())

        except asyncio.CancelledError:
            logger.info("Websocket reader cancelled")
            return
        except ChannelClosed:
            logger.error("Websocket channel closed")
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


async def gps_handler():
    from gps import client

    HOST = "127.0.0.1"
    PORT = 2947

    async with client.GpsdClient(HOST, PORT) as client:
        print(await client.poll())  # Get gpsd POLL response
        while True:
            print(await client.get_result())  # Get gpsd TPV responses

    # try:
    #     async with gps.aiogps.aiogps(
    #         connection_args={"host": "192.168.10.116", "port": 2947},
    #         connection_timeout=5,
    #         reconnect=0,  # do not try to reconnect, raise exceptions
    #         alive_opts={"rx_timeout": 5},
    #     ) as gpsd:
    #         async for msg in gpsd:
    #             logging.info(msg)
    # except asyncio.CancelledError:
    #     return
    # except asyncio.IncompleteReadError:
    #     logging.info("Connection closed by server")
    # except asyncio.TimeoutError:
    #     logging.error("Timeout waiting for gpsd to respond")
    # except Exception as exc:
    #     logging.error(f"Error: {exc}")


async def main():
    try:
        await remote_address()

        async with asyncio.TaskGroup() as tg:
            signal_channel: Channel[str] = Channel(8)
            comamnd_channel: Channel[str] = Channel(8)

            # TODO: Add GPS task
            task1 = tg.create_task(glonax(signal_channel, comamnd_channel))
            # task2 = tg.create_task(gps_handler())
            task3 = tg.create_task(websocket(signal_channel, comamnd_channel))
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
