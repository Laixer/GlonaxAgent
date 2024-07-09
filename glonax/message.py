import struct
from enum import Enum, IntEnum
from uuid import UUID

from pydantic import BaseModel, Field


class ControlType(IntEnum):
    HYDRAULIC_QUICK_DISCONNECT = 0x5
    HYDRAULIC_LOCK = 0x6
    HYDRAULIC_BOOST = 0x7
    HYDRAULIC_BOOM_CONFLUX = 0x8
    HYDRAULIC_ARM_CONFLUX = 0x9
    HYDRAULIC_BOOM_FLOAT = 0xA
    MACHINE_SHUTDOWN = 0x1B
    MACHINE_ILLUMINATION = 0x1C
    MACHINE_LIGHTS = 0x2D
    MACHINE_HORN = 0x1E
    MACHINE_STROBE_LIGHT = 0x1F
    MACHINE_TRAVEL_ALARM = 0x20


class Control(BaseModel):
    type: ControlType
    value: bool

    def to_bytes(self):
        return bytes([self.type.value, self.value])

    def from_bytes(data):
        return Control(type=ControlType(data[0]), value=bool(data[1]))


class Instance(BaseModel):
    id: UUID
    model: str
    machine_type: int
    version: tuple[int, int, int]
    serial_number: str

    @property
    def version_string(self):
        return f"{self.version[0]}.{self.version[1]}.{self.version[2]}"

    def from_bytes(data):
        id = UUID(bytes=data[:16])
        machine_type = data[16]
        version = struct.unpack("BBB", data[17:20])

        model_length = struct.unpack(">H", data[20:22])[0]
        model = data[22 : 22 + model_length].decode("utf-8")

        serial_number_length = struct.unpack(
            ">H", data[22 + model_length : 24 + model_length]
        )[0]
        serial_number = data[
            24 + model_length : 24 + model_length + serial_number_length
        ].decode("utf-8")

        return Instance(
            id=id,
            model=model,
            machine_type=machine_type,
            version=version,
            serial_number=serial_number,
        )

    def to_bytes(self):
        return (
            self.id.bytes
            + struct.pack("B", self.machine_type)
            + struct.pack("BBB", *self.version)
            + struct.pack(">H", len(self.model))
            + self.model.encode("utf-8")
            + struct.pack(">H", len(self.serial_number))
            + self.serial_number.encode("utf-8")
        )


class ModuleStatus(BaseModel):
    name: str
    state: int
    error_code: int

    def from_bytes(data):
        name_length = struct.unpack(">H", data[0:2])[0]
        name = data[2 : 2 + name_length].decode("utf-8")

        state = data[2 + name_length]
        error_code = data[3 + name_length]

        return ModuleStatus(name=name, state=state, error_code=error_code)

    def to_bytes(self):
        return (
            struct.pack(">H", len(self.name))
            + self.name.encode("utf-8")
            + struct.pack("BB", self.state, self.error_code)
        )


class EngineState(IntEnum):
    NOREQUEST = 0x0
    STARTING = 0x01
    STOPPING = 0x02
    REQUEST = 0x10


class Engine(BaseModel):
    driver_demand: int
    actual_engine: int
    rpm: int = Field(default=0, ge=0, le=8000)
    state: EngineState

    def request_rpm(rpm: int):
        return Engine(
            driver_demand=0, actual_engine=0, rpm=rpm, state=EngineState.REQUEST
        )

    def shutdown():
        return Engine(
            driver_demand=0, actual_engine=0, rpm=0, state=EngineState.NOREQUEST
        )

    def is_running(self):
        return self.state == EngineState.REQUEST and (
            self.actual_engine > 0 or self.rpm > 0
        )

    def from_bytes(data):
        driver_demand = data[0]
        actual_engine = data[1]
        rpm = struct.unpack(">H", data[2:4])[0]
        state = EngineState(data[4])

        return Engine(
            driver_demand=driver_demand,
            actual_engine=actual_engine,
            rpm=rpm,
            state=state,
        )

    def to_bytes(self):
        return (
            struct.pack("BB", self.driver_demand, self.actual_engine)
            + struct.pack(">H", self.rpm)
            + struct.pack("B", self.state)
        )


# TODO: Not part of glonax
# class Gnss(BaseModel):
#     location: tuple[float, float]
#     altitude: float
#     speed: float
#     heading: float
#     satellites: int

#     def from_bytes(data):
#         location = struct.unpack("ff", data[:8])
#         altitude, speed, heading = struct.unpack("fff", data[8:20])
#         satellites = struct.unpack("B", data[20:21])

#         return Gnss(
#             location=location,
#             altitude=altitude,
#             speed=speed,
#             heading=heading,
#             satellites=satellites[0],
#         )

#     def to_bytes(self):
#         return (
#             struct.pack("ff", *self.location)
#             + struct.pack("fff", self.altitude, self.speed, self.heading)
#             + struct.pack("B", self.satellites)
#         )


class RTCSessionDescription(BaseModel):
    type: str
    sdp: str


class ChannelMessageType(str, Enum):
    COMMAND = "command"
    SIGNAL = "signal"
    CONTROL = "control"
    PEER = "peer"
    ERROR = "error"


class Message(BaseModel):
    type: ChannelMessageType
    topic: str
    payload: Control | Instance | ModuleStatus | Engine | RTCSessionDescription
