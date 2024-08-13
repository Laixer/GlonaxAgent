import datetime
from pydantic import BaseModel
from dataclasses import dataclass


# TODO: Remove BaseModel, add dataclass
# TODO: Rename to HostTelemetry
class Telemetry(BaseModel):
    memory_used: float
    disk_used: float
    cpu_freq: float
    cpu_load: tuple[float, float, float]
    uptime: int
    created_at: datetime.timedelta | None = None


# TODO: Remove BaseModel, add dataclass
class GpsTelemetry(BaseModel):
    mode: int
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    speed: float | None = None


# TODO: Remove BaseModel, add dataclass
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
