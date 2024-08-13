import datetime
from dataclasses import asdict, dataclass


# TODO: Rename to HostTelemetry
@dataclass
class Telemetry:
    memory_used: float
    disk_used: float
    cpu_freq: float
    cpu_load: tuple[float, float, float]
    uptime: int
    created_at: datetime.timedelta | None = None

    def as_dict(self):
        return asdict(self)


@dataclass
class GpsTelemetry:
    mode: int
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    speed: float | None = None

    def as_dict(self):
        return asdict(self)


@dataclass
class HostConfig:
    # instance: UUID # TODO: Add this field
    hostname: str
    kernel: str
    memory_total: int
    cpu_count: int
    model: str
    version: str
    serial_number: str
    name: str | None = None

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
