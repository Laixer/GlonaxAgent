#!/usr/bin/env python3

import os
import time
import logging
import configparser
import argparse
import httpx
import psutil
import json
import asyncio
import websockets

from glonax import client as gclient
from glonax.client import Session
from glonax.message import Message, ChannelMessageType
from pydantic import ValidationError
from aiochannel import Channel, ChannelClosed, ChannelFull
from models import HostConfig, Telemetry


config = configparser.ConfigParser()
logger = logging.getLogger()


class MessageChangeDetector:
    def __init__(self):
        self.last_message: Message | None = None
        self.last_message_update = time.time()

    def process_message(self, message: Message) -> bool:
        has_changed = message != self.last_message or (
            time.time() - self.last_message_update > 15
        )
        self.last_message = message
        self.last_message_update = time.time()
        return has_changed

    def get_last_message(self) -> Message | None:
        return self.last_message


#     # TODO: Wrap this up in a class
#     status_map = {}
#     status_map_last_update = {}
#     # gnss_last: Gnss | None = None
#     # gnss_last_update = time.time()
#     engine_last: Engine | None = None
#     engine_last_update = time.time()

#     def on_status(self, status: ModuleStatus):
#         val = self.status_map.get(status.name)
#         last_update = self.status_map_last_update.get(status.name, 0)
#         last_update_elapsed = time.time() - last_update
#         if val is None or val != status or last_update_elapsed > 15:
#             logger.info(f"Status: {status}")

#             message = ChannelMessage(
#                 type="signal", topic="status", data=status.model_dump()
#             )

#             if is_connected and ws:
#                 # TODO: Only send if the connection is open
#                 ws.send(message.model_dump_json())

#             self.status_map[status.name] = status
#             self.status_map_last_update[status.name] = time.time()


INSTANCE: gclient.Instance | None = None

instance_event = asyncio.Event()


async def glonax(signal_channel: Channel[Message], command_channel: Channel[Message]):
    global INSTANCE, instance_event

    logger.info("Starting Glonax task")

    while True:
        try:
            path = config["glonax"]["unix_socket"]
            logger.info(f"Connecting to Glonax at {path}")

            reader, writer = await gclient.open_unix_connection(path)

            async with Session(reader, writer) as session:
                await session.handshake()

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
                        print("Command:", message)

                        if message.topic == "control":
                            await session.writer.control(message.payload)
                        elif message.topic == "engine":
                            await session.writer.engine(message.payload)

                async def read_session():
                    while True:
                        try:
                            message = await session.recv_message()
                            if message is not None:
                                signal_channel.put_nowait(message)

                        except ChannelFull:
                            logger.warning("Glonax signal channel is full")
                        except asyncio.IncompleteReadError as e:
                            logger.info("Glonax disconnected")
                            break

                await asyncio.gather(read_command_channel(), read_session())

        except asyncio.CancelledError:
            logger.info("Glonax task cancelled")
            return
        except ChannelClosed:
            logger.error("Glonax channel closed")
            return
        except ConnectionError as e:
            logger.error(f"Glonax connection error: {e}")
            await asyncio.sleep(1)


# TODO: Add more logging
async def websocket(
    signal_channel: Channel[Message], command_channel: Channel[Message]
):
    global INSTANCE, instance_event

    logger.debug("Waiting for instance event")

    await instance_event.wait()

    logger.info("Starting websocket task")

    engine_detector = MessageChangeDetector()

    while True:
        try:
            # TODO: Construct the URI properly from the config
            uri = f"wss://edge.laixer.equipment/api/{INSTANCE.id}/ws"
            # base_url = config["server"]["base_url"]
            # uri = f"ws://localhost:8000/{INSTANCE.id}/ws"
            async with websockets.connect(uri) as websocket:

                async def read_signal_channel():
                    async for message in signal_channel:
                        if message.topic == "engine":
                            if engine_detector.process_message(message):
                                await websocket.send(message.model_dump_json())
                        elif message.topic == "status":
                            # TODO: Only send status if it has changed
                            await websocket.send(message.model_dump_json())

                async def read_socket():
                    while True:
                        try:
                            message = await websocket.recv()
                            data = json.loads(message)

                            message = Message(**data)
                            if message.type == ChannelMessageType.COMMAND:
                                command_channel.put_nowait(message)

                        except json.JSONDecodeError:
                            print("Received raw message:", message)
                        except ValidationError as e:
                            print("Validation error:", e)

                await asyncio.gather(read_signal_channel(), read_socket())

        except asyncio.CancelledError:
            logger.info("Websocket reader cancelled")
            return
        except ChannelClosed:
            logger.error("Websocket channel closed")
            return
        except websockets.exceptions.ConnectionClosedError:
            logger.info("Websocket connection closed")
            await asyncio.sleep(1)
        except ConnectionResetError:
            logger.error("Websocket connection reset")
            await asyncio.sleep(1)
        except ConnectionRefusedError:
            logger.error("Websocket connection refused")
            await asyncio.sleep(1)


# async def update_host():
#     global INSTANCE, instance_event

#     logger.info("Starting host update task")

#     await instance_event.wait()

#     server_authkey = config["server"]["authkey"]
#     headers = {"Authorization": "Bearer " + server_authkey}

#     base_url = config["server"]["base_url"]
#     async with httpx.AsyncClient(
#         http2=True, base_url=base_url, headers=headers
#     ) as client:
#         while True:
#             try:
#                 host_config = HostConfig(
#                     hostname=os.uname().nodename,
#                     kernel=os.uname().release,
#                     memory_total=psutil.virtual_memory().total,
#                     cpu_count=psutil.cpu_count(),
#                     model=INSTANCE.model,
#                     version=INSTANCE.version_string,
#                     serial_number=INSTANCE.serial_number,
#                 )
#                 data = host_config.model_dump()

#                 response = await client.put(f"/{INSTANCE.id}/host", json=data)
#                 response.raise_for_status()

#             except asyncio.CancelledError:
#                 break
#             except httpx.HTTPStatusError as e:
#                 logger.error(f"HTTP error: {e}")
#             except httpx.ConnectError as e:
#                 logger.error(f"Connection error: {e}")
#             except httpx.ConnectTimeout as e:
#                 logger.error(f"Connection timeout: {e}")
#             except Exception as e:
#                 logger.error(f"Unknown error: {e}")
#             finally:
#                 await asyncio.sleep(60 * 20)


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


async def main():
    try:
        async with asyncio.TaskGroup() as tg:
            signal_channel: Channel[str] = Channel(8)
            comamnd_channel: Channel[str] = Channel(8)

            task1 = tg.create_task(glonax(signal_channel, comamnd_channel))
            # TODO: Create GPS task here
            task2 = tg.create_task(websocket(signal_channel, comamnd_channel))
            task3 = tg.create_task(update_telemetry())
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
    args = parser.parse_args()

    log_level = logging.getLevelName(args.log_level.upper())
    logging.basicConfig(level=log_level)

    config.read("config.ini")

    asyncio.run(main())
