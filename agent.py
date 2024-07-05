#!/usr/bin/env python3

import os
import time
import logging
import configparser
import httpx
import psutil
import json
import asyncio
import websockets

from glonax import client as gclient
from glonax.client import MessageType, Session
from glonax.message import Control, Engine, ModuleStatus
from pydantic import ValidationError

from models import ChannelMessage, HostConfig, Telemetry


logging.basicConfig(level=logging.INFO)

config = configparser.ConfigParser()
logger = logging.getLogger()


# class ForwardService(ServiceBase):
#     global is_connected

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

# def on_gnss(self, client: gclient.GlonaxClient, gnss: Gnss):
#     gnss_last_update_elapsed = time.time() - self.gnss_last_update
#     if self.gnss_last == gnss or gnss_last_update_elapsed > 15:
#         logger.info(f"GNSS: {gnss}")

#         message = ChannelMessage(
#             type="signal", topic="gnss", data=gnss.model_dump()
#         )

#         if is_connected and ws:
#             # TODO: Only send if the connection is open
#             ws.send(message.model_dump_json())

#         self.gnss_last = gnss
#         self.gnss_last_update = time.time()

# def on_engine(self, engine: Engine):
#     engine_last_update_elapsed = time.time() - self.engine_last_update
#     if self.engine_last != engine or engine_last_update_elapsed > 15:
#         logger.info(f"Engine: {engine}")
#         message = ChannelMessage(
#             type="signal", topic="engine", data=engine.model_dump()
#         )

#         if is_connected and ws:
#             # TODO: Only send if the connection is open
#             ws.send(message.model_dump_json())

#         self.engine_last = engine
#         self.engine_last_update = time.time()


from aiochannel import Channel, ChannelClosed, ChannelFull

INSTANCE: gclient.Instance | None = None

instance_event = asyncio.Event()


async def glonax(channel: Channel[str]):
    global INSTANCE, instance_event

    while True:
        try:
            reader, writer = await gclient.open_unix_connection()

            async with Session(reader, writer) as session:
                await session.handshake()

                logger.info(f"Instance ID: {session.instance.id}")
                logger.info(f"Instance model: {session.instance.model}")
                logger.info(f"Instance type: {session.instance.machine_type}")
                logger.info(f"Instance version: {session.instance.version_string}")
                logger.info(f"Instance serial number: {session.instance.serial_number}")

                INSTANCE = session.instance
                instance_event.set()

                while True:
                    try:
                        message_type, message = await session.reader.read()
                        if message_type == MessageType.STATUS:
                            status = ModuleStatus.from_bytes(message)
                            logger.info(f"Status: {status}")

                            message = ChannelMessage(type="signal", topic="status", data=status.model_dump())
                            channel.put_nowait(message.model_dump_json())

                        elif message_type == MessageType.ENGINE:
                            engine = Engine.from_bytes(message)
                            logger.info(f"Engine: {engine}")

                            message = ChannelMessage(type="signal", topic="engine", data=engine.model_dump())
                            channel.put_nowait(message.model_dump_json())

                        else:
                            logger.warning(f"glonax unknown message type: {message_type}")

                    except ChannelFull:
                        logger.warning("glonax channel is full")
                    except asyncio.IncompleteReadError as e:
                        logger.info("glonax reader disconnected")
                        break

        except asyncio.CancelledError:
            logger.info("glonax task cancelled")
            return
        except ChannelClosed:
            logger.error("glonax channel closed")
            return
        except ConnectionError as e:
            logger.error(f"glonax connection error: {e}")
            await asyncio.sleep(1)


async def websocket(channel: Channel[str]):
    global INSTANCE, instance_event

    await instance_event.wait()

    logger.info("Starting websocket task")

    uri = f"wss://edge.laixer.equipment/api/{INSTANCE.id}/ws"
    async with websockets.connect(uri) as websocket:

        message = ChannelMessage(type="signal", topic="boot")
        await websocket.send(message.model_dump_json())

        async def read_channel():
            async for item in channel:
                logger.info(f"Received: {item}")
                await websocket.send(item)

        async def read_socket():
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)  # Assuming JSON messages

                    message = ChannelMessage(**data)

                    if message.type == "command" and message.topic == "control":
                        control = Control(**message.data)
                        logger.info("Control:", control)

                        # await session.writer.control(control)

                    elif message.type == "command" and message.topic == "engine":
                        engine = Engine(**message.data)
                        logger.info("Engine:", engine)

                        # await session.writer.engine(engine)

                except json.JSONDecodeError:
                    print("Received raw message:", message)
                except ValidationError as e:
                    print("Validation error:", e)

                except asyncio.CancelledError:
                    logger.info("websocket reader cancelled")
                    break
                except websockets.exceptions.ConnectionClosedError:
                    # TODO: Reconnect
                    logger.info("Connection closed")
                    break
                except Exception as e:
                    logger.error(f"Error: {e}")

        await asyncio.gather(read_channel(), read_socket())


async def update_host():
    global INSTANCE, instance_event

    await instance_event.wait()

    headers = {"Authorization": "Bearer ABC@123"}

    base_url = f"https://edge.laixer.equipment/api/{INSTANCE.id}"
    async with httpx.AsyncClient(
        http2=True, base_url=base_url, headers=headers
    ) as client:
        while True:
            try:
                host_config = HostConfig(
                    hostname=os.uname().nodename,
                    kernel=os.uname().release,
                    model=INSTANCE.model,
                    version=378,  # TODO: Get the actual version
                    serial_number=INSTANCE.serial_number,
                )
                data = host_config.model_dump()

                response = await client.put(f"/host", json=data)
                response.raise_for_status()

            except asyncio.CancelledError:
                break
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e}")
            except httpx.ConnectError as e:
                logger.error(f"Connection error: {e}")
            except Exception as e:
                logger.error(f"Unknown error: {e}")
            finally:
                await asyncio.sleep(60 * 20)


async def update_telemetry():
    global INSTANCE, instance_event

    await instance_event.wait()

    def seconds_elapsed() -> int:
        return round(time.time() - psutil.boot_time())

    headers = {"Authorization": "Bearer ABC@123"}

    base_url = f"https://edge.laixer.equipment/api/{INSTANCE.id}"
    async with httpx.AsyncClient(
        http2=True, base_url=base_url, headers=headers
    ) as client:
        while True:
            try:
                telemetry = Telemetry(
                    memory_used=psutil.virtual_memory().percent,
                    disk_used=psutil.disk_usage("/").percent,
                    cpu_freq=psutil.cpu_freq().current,
                    cpu_load=psutil.getloadavg(),
                    uptime=seconds_elapsed(),
                )
                data = telemetry.model_dump()

                response = await client.post("/telemetry", json=data)
                response.raise_for_status()

            except asyncio.CancelledError:
                break
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e}")
            except httpx.ConnectError as e:
                logger.error(f"Connection error: {e}")
            except Exception as e:
                logger.error(f"Unknown error: {e}")

            await asyncio.sleep(60)


async def main():
    try:
        async with asyncio.TaskGroup() as tg:
            signal_channel: Channel[str] = Channel(8)

            task1 = tg.create_task(glonax(signal_channel))
            # TODO: Create GPS task here
            task2 = tg.create_task(websocket(signal_channel))
            task3 = tg.create_task(update_host())
            task4 = tg.create_task(update_telemetry())
    except asyncio.CancelledError:
        logger.info("Agent is gracefully shutting down")


if __name__ == "__main__":
    config.read("config.ini")

    # server_host = config["server"]["host"]
    # server_authkey = config["server"]["authkey"]

    asyncio.run(main())
