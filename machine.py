import time

from glonax.message import Engine


class MachineService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def feed(self, message: Engine):
        self.engine = message
        self.timestamp = time.time()

    def last_engine(self) -> Engine:
        return self.engine
