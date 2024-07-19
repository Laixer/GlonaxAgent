from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class Mode(IntEnum):
    UNKNOWN = 0
    NO_FIX = 1
    D2_FIX = 2
    D3_FIX = 3

    def __str__(self) -> str:
        return self.name


@dataclass
class Watch:
    enable: bool | None = True
    json: bool | None = True
    nmea: bool | None = False
    raw: int | None = None
    scaled: bool | None = False
    split24: bool | None = False
    pps: bool | None = False
    device: str = ""
    remote: str = ""
    timing: bool | None = False  # Undocumented

    @staticmethod
    def from_json(data: dict) -> "Watch":
        filtered_data = {k: v for k, v in data.items() if k in Watch.__annotations__}
        return Watch(**filtered_data)


@dataclass
class Version:
    release: str
    rev: str
    proto_major: int
    proto_minor: int
    remote: str | None = None

    @property
    def proto(self) -> tuple[int, int]:
        return self.proto_major, self.proto_minor

    @staticmethod
    def from_json(data: dict) -> "Version":
        filtered_data = {k: v for k, v in data.items() if k in Version.__annotations__}
        return Version(**filtered_data)


@dataclass
class Device:
    activated: datetime | None = None
    bps: int | None = None
    cycle: float | None = None
    driver: str | None = None
    flags: int | None = None
    hexdata: str | None = None
    mincycle: float | None = None
    native: int | None = None
    parity: str | None = None
    path: str | None = None
    readonly: bool | None = None
    sernum: str | None = None
    stopbits: int = 1
    subtype: str | None = None
    subtype1: str | None = None

    @staticmethod
    def from_json(data: dict) -> "Device":
        filtered_data = {k: v for k, v in data.items() if k in Device.__annotations__}
        return Device(**filtered_data)


@dataclass
class Devices:
    devices: list[Device]
    remote: str | None = None

    @staticmethod
    def from_json(data: dict) -> "Devices":
        filtered_data = {k: v for k, v in data.items() if k in Devices.__annotations__}
        return Devices(**filtered_data)


@dataclass
class TPV:
    device: str | None = None
    mode: Mode = Mode.UNKNOWN
    alt: float | None = None  # Deprecated
    altHAE: float | None = None
    altMSL: float | None = None
    ant: float | None = None
    climb: float | None = None
    clockbias: float | None = None
    clockdrift: float | None = None
    datum: str | None = None
    depth: float | None = None
    dgpsAge: float | None = None
    dgpsSta: int | None = None
    ecefx: float | None = None
    ecefy: float | None = None
    ecefz: float | None = None
    ecefpAcc: float | None = None
    ecefvx: float | None = None
    ecefvy: float | None = None
    ecefvz: float | None = None
    ecefvAcc: float | None = None
    epc: float | None = None
    epd: float | None = None
    eph: float | None = None
    eps: float | None = None
    ept: float | None = None
    epx: float | None = None
    epy: float | None = None
    epv: float | None = None
    geoidSep: float | None = None
    jam: float | None = None
    lat: float | None = None
    leapseconds: int | None = None
    lon: float | None = None
    magtrack: float | None = None
    magvar: float | None = None
    relD: float | None = None
    relE: float | None = None
    relN: float | None = None
    sep: float | None = None
    speed: float | None = None
    temp: float | None = None
    time: datetime | None = None
    track: float | None = None
    velD: float | None = None
    velE: float | None = None
    velN: float | None = None
    wanglem: float | None = None
    wangler: float | None = None
    wanglet: float | None = None
    wspeedr: float | None = None
    wspeedt: float | None = None
    wtemp: float | None = None

    @staticmethod
    def from_json(data: dict) -> "TPV":
        filtered_data = {k: v for k, v in data.items() if k in TPV.__annotations__}
        return TPV(**filtered_data)


@dataclass
class GST:
    device: str | None = None
    time: datetime | None = None
    rms: float | None = None
    major: float | None = None
    minor: float | None = None
    orient: float | None = None
    alt: float | None = None
    lat: float | None = None
    lon: float | None = None
    ve: float | None = None
    vn: float | None = None
    vu: float | None = None

    @staticmethod
    def from_json(data: dict) -> "GST":
        filtered_data = {k: v for k, v in data.items() if k in GST.__annotations__}
        return GST(**filtered_data)


# TODO: Check
@dataclass
class ATT:
    device: str | None = None
    time: datetime | None = None
    heading: float | None = None
    magSt: float | None = None
    pitch: float | None = None
    roll: float | None = None
    yaw: float | None = None
    dip: float | None = None
    magLen: float | None = None
    pitchSt: float | None = None
    rollSt: float | None = None
    yawSt: float | None = None


# TODO: Check
@dataclass
class TOFF:
    device: str | None = None
    time: datetime | None = None
    clockOffset: float | None = None
    leapSec: int | None = None
    leapSecErr: float | None = None
    timeRes: float | None = None
    timeRef: str | None = None


# TODO: Check
@dataclass
class PPS:
    device: str | None = None
    time: datetime | None = None


# TODO: Check
@dataclass
class OSC:
    device: str | None = None
    time: datetime | None = None


@dataclass
class PRN:
    PRN: int
    used: bool
    az: float | None = None
    el: float | None = None
    freqid: int | None = None
    gnssid: int | None = None
    health: int | None = None
    ss: float | None = None
    sigid: int | None = None
    svid: int | None = None


@dataclass
class Sky:
    time: datetime
    device: str | None = None
    nSat: int | None = None
    gdop: float | None = None
    hdop: float | None = None
    pdop: float | None = None
    pr: float | None = None
    prRate: float | None = None
    prRes: float | None = None
    qual: float | None = None
    satellites: list[PRN] | None = None
    tdop: float | None = None
    uSat: int | None = None
    vdop: float | None = None
    xdop: float | None = None
    ydop: float | None = None

    @staticmethod
    def from_json(data: dict) -> "Sky":
        filtered_data = {k: v for k, v in data.items() if k in Sky.__annotations__}
        return Sky(**filtered_data)


@dataclass
class Poll:
    time: datetime
    active: int
    tpv: list[TPV]
    sky: list[Sky]

    @staticmethod
    def from_json(data: dict) -> "Poll":
        filtered_data = {k: v for k, v in data.items() if k in Poll.__annotations__}
        return Poll(**filtered_data)


@dataclass
class Error:
    message: str

    def __str__(self) -> str:
        return self.message

    @staticmethod
    def from_json(data: dict) -> "Error":
        filtered_data = {k: v for k, v in data.items() if k in Error.__annotations__}
        return Error(**filtered_data)
