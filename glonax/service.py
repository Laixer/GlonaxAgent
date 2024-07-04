from abc import abstractmethod

from glonax.client import MessageType
from glonax.message import Engine, ModuleStatus


class ServiceBase:
    def __call__(self, message_type: MessageType, message: bytes):
        if message_type == MessageType.STATUS:
            status = ModuleStatus.from_bytes(message)
            self.on_status(status)
        elif message_type == MessageType.ENGINE:
            engine = Engine.from_bytes(message)
            self.on_engine(engine)

    @abstractmethod
    def on_status(self, status: ModuleStatus):
        pass

    @abstractmethod
    def on_motion(self, motion):
        pass

    @abstractmethod
    def on_engine(self, engine: Engine):
        pass

    @abstractmethod
    def on_control(self, control):
        pass

    @abstractmethod
    def on_rotator(self, rotator):
        pass
