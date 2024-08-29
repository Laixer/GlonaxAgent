import time

from glonax_agent.models import GpsTelemetry


class LocationService:
    def __init__(self):
        self.location = None

    def feed(self, location: GpsTelemetry):
        self.location = location
        self.timestamp = time.time()

    @property
    def last_location(self) -> GpsTelemetry | None:
        return self.location

    @property
    def current_location(self) -> GpsTelemetry | None:
        if self.location is None:
            return None
        if time.time() - self.timestamp > 30:
            return None
        return self.location

    @property
    def has_fix(self) -> bool:
        if self.location is None:
            return False
        return self.location.fix
