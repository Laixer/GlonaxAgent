import json
import struct
from enum import IntEnum
from uuid import UUID
from dataclasses import asdict, dataclass


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


@dataclass
class Control:
    type: ControlType
    value: bool

    def to_bytes(self):
        return bytes([self.type.value, self.value])

    def from_bytes(data):
        return Control(type=ControlType(data[0]), value=bool(data[1]))

    def json(self):
        return json.dumps(asdict(self))

    def from_json(data):
        return Control(**json.loads(data))


@dataclass
class Instance:
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

    def json(self):
        return json.dumps(asdict(self))

    def from_json(data):
        return Instance(**json.loads(data))


@dataclass
class ModuleStatus:
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

    def json(self):
        return json.dumps(asdict(self))

    def from_json(data):
        return ModuleStatus(**json.loads(data))


class EngineState(IntEnum):
    NOREQUEST = 0x0
    STARTING = 0x01
    STOPPING = 0x02
    REQUEST = 0x10


@dataclass
class Engine:
    driver_demand: int
    actual_engine: int
    rpm: int
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

    def json(self):
        return json.dumps(asdict(self))

    def from_json(data):
        return Engine(**json.loads(data))


class MotionType(IntEnum):
    STOP_ALL = 0x00
    RESUME_ALL = 0x01
    RESET_ALL = 0x02
    STRAIGHT_DRIVE = 0x05
    CHANGE = 0x10


@dataclass
class MotionChangeSet:
    actuator: int
    value: int

    def from_bytes(data):
        actuator = struct.unpack(">H", data[0:2])[0]
        value = struct.unpack(">h", data[2:4])[0]

        return MotionChangeSet(actuator=actuator, value=value)

    def to_bytes(self):
        return struct.pack(">H", self.actuator) + struct.pack(">h", self.value)


@dataclass
class MotionStraightDrive:
    value: int

    def from_bytes(data):
        value = struct.unpack(">h", data[0:2])[0]

        return MotionStraightDrive(value=value)

    def to_bytes(self):
        return struct.pack(">h", self.value)


@dataclass
class Motion:
    type: MotionType
    straigh_drive: MotionStraightDrive | None = None
    change: list[MotionChangeSet] | None = None

    def stop_all():
        return Motion(type=MotionType.STOP_ALL)

    def resume_all():
        return Motion(type=MotionType.RESUME_ALL)

    def reset_all():
        return Motion(type=MotionType.RESET_ALL)

    def straight_drive(value: int):
        return Motion(
            type=MotionType.STRAIGHT_DRIVE,
            straigh_drive=MotionStraightDrive(value=value),
        )

    def from_bytes(data):
        type = MotionType(data[0])

        if type == MotionType.CHANGE:
            change = []
            offset = 1
            while offset < len(data):
                change.append(MotionChangeSet.from_bytes(data[offset : offset + 4]))
                offset += 4
            return Motion(type=type, change=change)
        elif type == MotionType.STRAIGHT_DRIVE:
            return Motion(
                type=type, straigh_drive=MotionStraightDrive.from_bytes(data[1:])
            )
        else:
            return Motion(type=type)

    def to_bytes(self):
        if self.change:
            return (
                struct.pack("B", self.type)
                + struct.pack("B", len(self.change))
                + b"".join([change.to_bytes() for change in self.change])
            )
        elif self.straigh_drive:
            return struct.pack("B", self.type) + self.straigh_drive.to_bytes()
        else:
            return struct.pack("B", self.type)

    def json(self):
        return json.dumps(asdict(self))

    def from_json(data):
        return Motion(**json.loads(data))


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
