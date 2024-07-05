import datetime
from pydantic import BaseModel


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
    memory_total: int
    cpu_count: int
    model: str
    version: str
    serial_number: str
