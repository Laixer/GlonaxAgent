import time
import logging

from glonax.message import Engine, Instance, ModuleStatus, Motion

logger = logging.getLogger(__name__)


class MachineService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "instance"):
            self.instance = None
        if not hasattr(self, "engine"):
            self.engine = None
        if not hasattr(self, "module_status"):
            self.module_status = {}
        if not hasattr(self, "motion"):
            self.motion = None

    def feed(self, message):
        if isinstance(message, Instance):
            if self.instance is None or self.instance != message:
                self.instance = message
        if isinstance(message, Engine):
            if self.engine is None or self.engine != message:
                self.engine = message
                logger.info(f"Engine changed: {message}")
        elif isinstance(message, ModuleStatus):
            last_module_status = self.module_status.get(message.name)
            if last_module_status is None or last_module_status != message:
                self.module_status[message.name] = message
                logger.info(f"Module status changed: {message}")
        elif isinstance(message, Motion):
            if self.motion is None or self.motion != message:
                self.motion = message
                logger.info(f"Motion changed: {message}")
        self.timestamp = time.time()

    @property
    def instance(self) -> Instance:
        return self.instance

    @property
    def last_engine(self) -> Engine | None:
        return self.engine

    @property
    def last_motion(self) -> Motion | None:
        return self.motion

    def last_module_status(self, name: str) -> ModuleStatus | None:
        return self.module_status.get(name)
