import time
import logging

from glonax.message import Engine, Instance, ModuleStatus, Motion

logger = logging.getLogger(__name__)


class MachineService:
    def __init__(self):
        self._instance = None
        self._engine = None
        self.module_status = {}
        self._motion = None

    def feed(self, message):
        if isinstance(message, Instance):
            if self._instance is None or self._instance != message:
                self._instance = message
        if isinstance(message, Engine):
            if self._engine is None or self._engine != message:
                self._engine = message
                logger.debug(f"Engine changed: {message}")
        elif isinstance(message, ModuleStatus):
            last_module_status = self.module_status.get(message.name)
            if last_module_status is None or last_module_status != message:
                self.module_status[message.name] = message
                logger.debug(f"Module status changed: {message}")
        elif isinstance(message, Motion):
            if self._motion is None or self._motion != message:
                self._motion = message
                logger.debug(f"Motion changed: {message}")
        self.timestamp = time.time()

    @property
    def instance(self) -> Instance:
        return self._instance

    @property
    def last_engine(self) -> Engine | None:
        return self._engine

    @property
    def last_motion(self) -> Motion | None:
        return self._motion

    def last_module_status(self, name: str) -> ModuleStatus | None:
        return self.module_status.get(name)
