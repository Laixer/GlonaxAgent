import time
import logging


logger = logging.getLogger(__name__)


class NetworkService:
    def __init__(self):
        self._latency = None
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
