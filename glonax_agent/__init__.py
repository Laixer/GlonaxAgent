import os
import pickle
import logging

from glonax.message import Instance
from glonax_agent.host import HostService
from glonax_agent.location import LocationService
from glonax_agent.machine import MachineService
from glonax_agent.management import ManagementService
from glonax_agent.network import NetworkService


def _load_cache(file: str = "instance.dat") -> Instance | None:
    try:
        with open(file, "rb") as f:
            return pickle.load(f)

    except FileNotFoundError:
        return
    # TODO: Should be more specific
    except Exception:
        os.remove("instance.dat")


def _dump_cache(
    instance: Instance,
    file: str = "instance.dat",
):
    with open(file, "wb") as f:
        pickle.dump(instance, f)


class GlonaxAgent:
    host_service = HostService()
    location_service = LocationService()
    machine_service = MachineService()
    network_service = NetworkService()

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        # self.logger.setLevel(logging.DEBUG)
        # self.logger.addHandler(logging.StreamHandler())
        self.logger.info("GlonaxAgent initialized")

        self.instance = _load_cache()
        if self.instance is None:
            # TODO: Connect to Glonax
            pass

        assert self.instance is not None

        _dump_cache(self.instance)
        # self.machine_service.feed(_instance)

        self.logger.info(f"Instance ID: {self.instance.id}")
        self.logger.info(f"Instance model: {self.instance.model}")
        self.logger.info(f"Instance type: {self.instance.machine_type}")
        self.logger.info(f"Instance version: {self.instance.version_string}")
        self.logger.info(f"Instance serial number: {self.instance.serial_number}")

        self.management_service = ManagementService(
            self.config["telemetry"]["base_url"],
            self.config["telemetry"]["token"],
            self.instance.id,
        )

    async def _boot(self):
        ip = await self.management_service.remote_ip()
        self.logger.info(f"Remote address: {ip}")
        self.network_service.set_remote_addr(ip)

        self.machine_service.feed(self.instance)

    async def _notify(self, topic: str, message: str):
        await self.management_service.notify(topic, message)
