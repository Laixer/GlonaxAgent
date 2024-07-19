from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class Mode(IntEnum):
    UNKNOWN = 0
    NO_FIX = 1
    TWO_D_FIX = 2
    THREE_D_FIX = 3

    def __str__(self) -> str:
        return self.name


@dataclass
class Watch:
    enable: bool = True
    json: bool = True
    split24: bool = False
    nmea: bool = False
    scaled: bool = False
    pps: bool = False
    timing: bool = False
    raw: int = 0


@dataclass
class Version:
    release: str
    rev: str
    proto_major: int
    proto_minor: int

    @property
    def proto(self) -> tuple[int, int]:
        return self.proto_major, self.proto_minor


@dataclass
class Device:
    path: str
    driver: str | None = None
    subtype: str | None = None
    activated: datetime | None = None
    flags: int | None = None
    native: int | None = None
    bps: int | None = None
    parity: str | None = None
    stopbits: int | None = None
    cycle: float | None = None
    mincycle: float | None = None


@dataclass
class Devices:
    devices: list[Device]


@dataclass
class TPV:
    device: str | None = None
    mode: Mode = Mode.UNKNOWN
    time: datetime | None = None
    ept: float | None = None
    lat: float | None = None
    lon: float | None = None
    altHAE: float | None = None
    altMSL: float | None = None
    alt: float | None = None
    epx: float | None = None
    epy: float | None = None
    epv: float | None = None
    track: float | None = None
    magtrack: float | None = None
    magvar: float | None = None
    speed: float | None = None
    climb: float | None = None
    eps: float | None = None
    epc: float | None = None
    geoidSep: float | None = None
    eph: float | None = None
    sep: float | None = None
    leapseconds: int | None = None
    ecefx: float | None = None
    ecefy: float | None = None
    ecefz: float | None = None
    ecefvx: float | None = None
    ecefvy: float | None = None
    ecefvz: float | None = None


@dataclass
class PRN:
    PRN: int
    used: bool
    gnssid: int
    svid: int
    el: float | None = None
    az: float | None = None
    ss: float | None = None


@dataclass
class Sky:
    device: str
    nSat: int
    uSat: int
    time: datetime
    xdop: float | None = None
    ydop: float | None = None
    vdop: float | None = None
    tdop: float | None = None
    hdop: float | None = None
    gdop: float | None = None
    pdop: float | None = None
    satellites: list[PRN] | None = None


@dataclass
class Poll:
    time: datetime
    active: int
    tpv: list[TPV]
    sky: list[Sky]
