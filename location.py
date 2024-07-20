from dataclasses import dataclass


@dataclass
class Location:
    fix: bool
    latitude: float
    longitude: float
    speed: float
    altitude: float
    heading: float


class LocationService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def set_location(self, location: Location):
        self.location = location

    def get_location(self):
        return self.location
