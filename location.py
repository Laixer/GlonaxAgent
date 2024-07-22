import time
from dataclasses import dataclass


@dataclass
class Location:
    fix: bool = False
    latitude: float | None = None
    longitude: float | None = None
    speed: float | None = None
    altitude: float | None = None
    heading: float | None = None


class LocationService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "location"):
            self.location = None

    def feed(self, location: Location):
        self.location = location
        self.timestamp = time.time()

    def last_location(self) -> Location | None:
        return self.location

    def has_fix(self) -> bool:
        if self.location is None:
            return False
        return self.location.fix
