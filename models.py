import datetime
from pydantic import BaseModel


# TODO: Rename to HostTelemetry
class Telemetry(BaseModel):
    memory_used: float
    disk_used: float
    cpu_freq: float
    cpu_load: tuple[float, float, float]
    uptime: int
    created_at: datetime.timedelta | None = None


class GpsTelemetry(BaseModel):
    mode: int
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    speed: float | None = None


class HostConfig(BaseModel):
    # instance: UUID # TODO: Add this field
    name: str | None = None
    hostname: str
    kernel: str
    memory_total: int
    cpu_count: int
    model: str
    version: str
    serial_number: str


class PeerConnectionParams:
    video_track: int = 0
    video_size: str = "1280x720"
