import datetime
from dataclasses import asdict, dataclass


@dataclass
class HostTelemetry:
    instance: str
    hostname: str
    kernel: str
    model: str
    version: str
    serial_number: str
    memory_used: float
    memory_total: int
    disk_used: float
    cpu_freq: float
    cpu_load: tuple[float, float, float]
    cpu_count: int
    uptime: int

    def as_dict(self):
        return asdict(self)


@dataclass
class GpsTelemetry:
    instance: str
    mode: int
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    speed: float | None = None
    heading: float | None = None

    def __str__(self):
        return f"Location ({round(self.lat, 5)}, {round(self.lon, 5)})"

    def as_dict(self):
        return asdict(self)


@dataclass
class GlonaxPeerConnectionParams:
    connection_id: int
    video_track: int = 0
    user_agent: str = "glonax-rtc/1.0"


@dataclass
class RTCIceCandidateParams:
    candidate: str
    sdpMid: str
    sdpMLineIndex: int
    usernameFragment: str
