import time
import logging


logger = logging.getLogger(__name__)


class NetworkService:
    __cls_instance = None

    def __new__(cls):
        if cls.__cls_instance is None:
            cls.__cls_instance = super().__new__(cls)
        return cls.__cls_instance

    def __init__(self):
        if not hasattr(self, "_latency"):
            self._latency = None
        if not hasattr(self, "_remote_addr"):
            self._remote_addr = None

    def feed_latency(self, latency):
        self._latency = latency
        self.timestamp = time.time()

    def set_remote_addr(self, remote_addr):
        self._remote_addr = remote_addr

    @property
    def latency(self) -> float | None:
        return self._latency

    @property
    def remote_addr(self) -> str | None:
        return self._remote_addr
