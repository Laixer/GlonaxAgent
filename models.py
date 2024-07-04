import datetime
from pydantic import BaseModel


class ChannelMessage(BaseModel):
    type: str
    topic: str
    data: dict | None = None


class Telemetry(BaseModel):
    memory_used: float
    disk_used: float
    cpu_freq: float
    cpu_load: tuple[float, float, float]
    uptime: int
    created_at: datetime.timedelta | None = None


class HostConfig(BaseModel):
    # instance: UUID # TODO: Add this field
    name: str | None = None
    hostname: str
    kernel: str
    # memory_total: int # TODO: Add this field
    # cpu_count: int # TODO: Add this field
    model: str
    version: int  # TODO: Change this to a string
    serial_number: str
