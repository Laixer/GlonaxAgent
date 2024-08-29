#!/usr/bin/env python3

import pickle
import logging
import configparser
import argparse
import traceback
import asyncio

from systemd import journal

from log import ColorLogHandler
from glonax import client as gclient

from glonax_agent import GlonaxAgent
from glonax_agent.system import System
from glonax_agent.models import GpsTelemetry

config = configparser.ConfigParser()
logger = logging.getLogger()

glonax_agent: GlonaxAgent | None = None


async def update_telemetry():
    global glonax_agent

    logger.info("Starting telemetry task")

    while True:
        await asyncio.sleep(15)

        telemetry = glonax_agent.host_service.get_telemetry(glonax_agent.instance)
        await glonax_agent.management_service.update_host_telemetry(telemetry)

        await asyncio.sleep(5)

        if glonax_agent.location_service.current_location is not None:
            await glonax_agent.management_service.update_gps_telemetry(
                glonax_agent.location_service.current_location
            )

        await asyncio.sleep(15)

        # logger.info(f"Engine: {machine_service.last_engine}")
        # logger.info(f"Motion: {machine_service.last_motion}")

        # machine_service.last_module_status(module)

        # TODO: Send telemetry last engine and last motion
        # TODO: Send telemetry module status

        await asyncio.sleep(25)


async def gps_server():
    from gps import client
    from gps.schemas import TPV

    global glonax_agent

    while True:
        try:
            async with await client.open() as c:
                async for result in c:
                    if isinstance(result, TPV):
                        location = GpsTelemetry(
                            instance=str(glonax_agent.instance.id),
                            mode=result.mode,
                            lat=result.lat,
                            lon=result.lon,
                            alt=result.alt,
                            speed=result.speed,
                            heading=result.track,
                        )

                        logger.debug(location)
                        glonax_agent.location_service.feed(location)

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


async def ping_server():
    host = config["ping"]["host"]

    global glonax_agent

    while True:
        try:
            await asyncio.sleep(7)

            latency = await System.ping(host)

            logger.debug(f"Network latency {latency} ms")
            glonax_agent.network_service.feed_latency(latency)

        except asyncio.CancelledError:
            logger.info("Ping handler cancelled")
            return
        except Exception as e:
            logger.critical(f"Unknown error: {traceback.format_exc()}")


async def glonax_server():
    global glonax_agent

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

                async for message in session:
                    glonax_agent.machine_service.feed(message)

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
    global glonax_agent

    glonax_agent = GlonaxAgent(config)

    logger.info("Starting agent")

    try:
        await glonax_agent._boot()

        await glonax_agent._notify(
            "AGENT.START", f"Agent {glonax_agent.instance.id} started"
        )

        async with asyncio.TaskGroup() as tg:
            task1 = tg.create_task(glonax_server())
            task2 = tg.create_task(ping_server())
            task3 = tg.create_task(gps_server())
            task5 = tg.create_task(update_telemetry())

    except asyncio.CancelledError:
        await glonax_agent._notify(
            "AGENT.SHUTDOWN", f"Agent {glonax_agent.instance.id} shutting down"
        )

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
