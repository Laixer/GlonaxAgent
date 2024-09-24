import logging

from glonax.message import Instance
from glonax_agent.host import HostService
from glonax_agent.location import LocationService
from glonax_agent.machine import MachineService
from glonax_agent.management import ManagementService
from glonax_agent.media import MediaService
from glonax_agent.network import NetworkService


class GlonaxAgent:
    host_service = HostService()
    location_service = LocationService()
    machine_service = MachineService()
    network_service = NetworkService()
    media_service = MediaService()

    def __init__(self, config, instance: Instance):
        self.config = config
        self.instance = instance
        self.logger = logging.getLogger(__name__)
        self.logger.info("GlonaxAgent initialized")

        self.machine_service.feed(self.instance)

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
        pass
        # ip = await self.management_service.remote_ip()
        # self.logger.info(f"Remote address: {ip}")
        # self.network_service.set_remote_addr(ip)

    async def _notify(self, topic: str, message: str):
        pass
        # await self.management_service.notify(topic, message)
