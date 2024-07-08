from datetime import datetime
from enum import IntEnum
from typing import Literal, Optional, Union

from pydantic import BaseModel, RootModel, Extra, Field


class Mode(IntEnum):
    unknown = 0
    no_fix = 1
    two_d_fix = 2
    three_d_fix = 3


class Watch(BaseModel):
    # class_: Literal["WATCH"] = Field("WATCH", alias="class")
    enable: bool = True
    json_: bool = Field(True, alias="json")
    split24: bool = False
    raw: int = 0

    class Config:
        extra = Extra.allow


class Version(BaseModel):
    # class_: Literal["VERSION"] = Field(alias="class")
    release: str
    rev: str
    proto_major: int
    proto_minor: int

    @property
    def proto(self) -> tuple[int, int]:
        return self.proto_major, self.proto_minor


class Device(BaseModel):
    # class_: Literal["DEVICE"] = Field(alias="class")
    path: str
    driver: str
    subtype: str
    activated: datetime
    flags: int
    native: int
    bps: int
    parity: str
    stopbits: int
    cycle: float
    mincycle: float


class Devices(BaseModel):
    # class_: Literal["DEVICES"] = Field(alias="class")
    devices: list[Device]


class TPV(BaseModel):
    # class_: Literal["TPV"] = Field(alias="class")
    device: str
    mode: Mode
    time: datetime
    ept: float
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


class PRN(BaseModel):
    PRN: int
    el: float | None = None
    az: float
    ss: float
    used: bool
    gnssid: int
    svid: int


class Sky(BaseModel):
    # class_: Literal["SKY"] = Field(alias="class")
    device: str
    xdop: float | None = None
    ydop: float | None = None
    vdop: float
    tdop: float
    hdop: float
    gdop: float
    pdop: float
    nSat: int
    uSat: int
    satellites: list[PRN]


class Poll(BaseModel):
    # class_: Literal["POLL"] = Field(alias="class")
    time: datetime
    active: int
    tpv: list[TPV]
    sky: list[Sky]


# class Response(BaseModel):
#     __root__: Union[Poll, Sky, TPV, Devices, Version, Watch] = Field(
#         discriminator="class_"
#     )


# class Response(RootModel):
#     __root__: Union[Poll, Sky, TPV, Devices, Version, Watch] = Field(
#         discriminator="class_", alias="class"
#     )
Response = RootModel[Poll | Sky | TPV | Devices | Version | Watch]
