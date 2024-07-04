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


async def update_host(instance: gclient.Instance):
    host_config = HostConfig(
        hostname=os.uname().nodename,
        kernel=os.uname().release,
        model=instance.model,
        version=378,
        serial_number=instance.serial_number,
    )
    data = host_config.model_dump()

    headers = {"Authorization": "Bearer ABC@123"}

    async with httpx.AsyncClient(http2=True) as client:
        while True:
            try:
                response = await client.put(
                    f"https://edge.laixer.equipment/api/{instance.id}/host",
                    json=data,
                    headers=headers,
                )
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
                await asyncio.sleep(60 * 60)


async def update_telemetry(instance: gclient.Instance):
    def seconds_elapsed() -> int:
        return round(time.time() - psutil.boot_time())

    telemetry = Telemetry(
        memory_used=psutil.virtual_memory().percent,
        disk_used=psutil.disk_usage("/").percent,
        cpu_freq=psutil.cpu_freq().current,
        cpu_load=psutil.getloadavg(),
        uptime=seconds_elapsed(),
    )
    data = telemetry.model_dump()

    headers = {"Authorization": "Bearer ABC@123"}

    async with httpx.AsyncClient(http2=True) as client:
        while True:
            try:
                response = await client.post(
                    f"https://edge.laixer.equipment/api/{instance.id}/telemetry",
                    json=data,
                    headers=headers,
                )
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
                await asyncio.sleep(60)


async def glonax_reader(
    session: Session, websocket: websockets.WebSocketClientProtocol
):
    while True:
        try:
            message_type, message = await session.reader.read()
            if message_type == MessageType.STATUS:
                status = ModuleStatus.from_bytes(message)
                logger.info(f"Status: {status}")

                # message = ChannelMessage(
                #     type="signal", topic="status", data=status.model_dump()
                # )

                # await websocket.send(message.model_dump_json())

            elif message_type == MessageType.ENGINE:
                engine = Engine.from_bytes(message)
                logger.info(f"Engine: {engine}")

                message = ChannelMessage(
                    type="signal", topic="engine", data=engine.model_dump()
                )
                await websocket.send(message.model_dump_json())

            else:
                logger.warning(f"Unknown message type: {message_type}")

        except asyncio.CancelledError:
            logger.info("glonax reader cancelled")
            break
        except asyncio.IncompleteReadError as e:
            # TODO: Reconnect
            logger.info("Connection closed")
            break
        except Exception as e:
            logger.error(f"Error: {e}")


async def websocket_reader(
    session: Session, websocket: websockets.WebSocketClientProtocol
):
    message = ChannelMessage(type="signal", topic="boot")
    await websocket.send(message.model_dump_json())

    while True:
        try:
            message = await websocket.recv()
            data = json.loads(message)  # Assuming JSON messages

            message = ChannelMessage(**data)

            if message.type == "command" and message.topic == "control":
                control = Control(**message.data)
                logger.info("Control:", control)

                await session.writer.control(control)

            elif message.type == "command" and message.topic == "engine":
                engine = Engine(**message.data)
                logger.info("Engine:", engine)

                await session.writer.engine(engine)

            # except json.JSONDecodeError:
            #     print("Received raw message:", message)
            # except ValidationError as e:
            #     print("Validation error:", e)

        except asyncio.CancelledError:
            logger.info("websocket reader cancelled")
            break
        except websockets.exceptions.ConnectionClosedError:
            # TODO: Reconnect
            logger.info("Connection closed")
            break
        except Exception as e:
            logger.error(f"Error: {e}")

    # MOVE
    await websocket.close()


async def main():
    try:
        reader, writer = await gclient.open_unix_connection()

        async with Session(reader, writer) as session:
            await session.handshake()

            # TODO: Open GPS connection

            uri = f"wss://edge.laixer.equipment/api/{session.instance.id}/ws"
            w = await websockets.connect(uri)

            logger.info(f"Instance ID: {session.instance.id}")
            logger.info(f"Instance model: {session.instance.model}")
            logger.info(f"Instance type: {session.instance.machine_type}")
            logger.info(f"Instance version: {session.instance.version_string}")
            logger.info(f"Instance serial number: {session.instance.serial_number}")

            async with asyncio.TaskGroup() as tg:
                task1 = tg.create_task(glonax_reader(session, w))
                task2 = tg.create_task(websocket_reader(session, w))
                task3 = tg.create_task(update_host(session.instance))
                task4 = tg.create_task(update_telemetry(session.instance))
    except asyncio.CancelledError:
        logger.info("Agent is gracefully shutting down")
    except ConnectionError as e:
        # TODO: Reconnect
        logger.error(f"Connection error: {e}")


if __name__ == "__main__":
    config.read("config.ini")

    server_host = config["server"]["host"]
    server_authkey = config["server"]["authkey"]

    asyncio.run(main())
