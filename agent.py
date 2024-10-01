#!/usr/bin/env python3

import os
import logging
import configparser
import argparse
import traceback
import asyncio

from systemd import journal
from log import ColorLogHandler
from glonax import client as gclient
from glonax.message import Instance

from glonax_agent import GlonaxAgent
from glonax_agent.system import System
from glonax_agent.models import GpsTelemetry

APP_NAME = "glonax-agent"

config = configparser.ConfigParser()
logger = logging.getLogger()

instance_id = os.getenv("GLONAX_INSTANCE_ID")


async def gps_server():
    from gps import client
    from gps.schemas import TPV

    while True:
        try:
            async with await client.open() as c:
                async for result in c:
                    if isinstance(result, TPV):
                        location = GpsTelemetry(
                            # instance=str(glonax_agent.instance.id),
                            mode=result.mode,
                            lat=result.lat,
                            lon=result.lon,
                            alt=result.alt,
                            speed=result.speed,
                            heading=result.track,
                        )

                        logger.debug(location)
                        # glonax_agent.location_service.feed(location)

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


async def glonax_server():
    logger.info("Starting glonax task")

    path = config["glonax"]["unix_socket"]

    while True:
        try:
            logger.info(f"Connecting to glonax at {path}")

            user_agent = "glonax-agent/1.0"
            async with await gclient.open_session(
                path, user_agent=user_agent
            ) as session:
                logger.info(f"Glonax connected to {path}")

                # async for message in session:
                #     glonax_agent.machine_service.feed(message)

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


async def main():
    logger.info(f"Starting {APP_NAME}")

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(glonax_server())
            tg.create_task(gps_server())

    except asyncio.CancelledError:
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
    parser.add_argument(
        "-i",
        "--instance",
        default=instance_id,
        help="Specify the instance ID to use",
    )
    # parser.add_argument(
    #     "-s",
    #     "--socket",
    #     default=UNIX_SOCKET,
    #     help="Specify the UNIX socket path to use",
    # )
    args = parser.parse_args()

    log_level = logging.getLevelName(args.log_level.upper())
    logger.setLevel(log_level)

    if args.log_systemd:
        logger.addHandler(journal.JournaldLogHandler(identifier=APP_NAME))
    else:
        logger.addHandler(ColorLogHandler())

    config.read(args.config)
    config["DEFAULT"]["instance_id"] = args.instance
    # config["glonax"]["unix_socket"] = args.socket

    asyncio.run(main())
