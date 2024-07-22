import asyncio
import json
import logging
from dataclasses import asdict

from gps.schemas import GST, TPV, Device, Devices, Error, Sky, Version, Watch, Poll

POLL = "?POLL;\r\n"
WATCH = "?WATCH={}\r\n"

logger = logging.getLogger(__name__)


class Client:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        watch_config: Watch = Watch(),
    ):
        self.__reader = reader
        self.__writer = writer

        self._version = None
        self._devices = None
        self._watch = None

        self.watch_config = watch_config

    async def __read(self) -> dict:
        try:
            data = await self.__reader.readline()
            return json.loads(data)
        except asyncio.IncompleteReadError:
            raise ConnectionError("Connection closed by server")

    async def close(self):
        await self.__writer.drain()
        self.__writer.close()
        await self.__writer.wait_closed()

    @staticmethod
    def __class_factory(data: dict) -> object:
        class_type = data.get("class").upper()

        match class_type:
            case "TPV":
                return TPV.from_json(data)
            case "VERSION":
                return Version.from_json(data)
            case "DEVICES":
                return Devices.from_json(data)
            case "DEVICE":
                return Device.from_json(data)
            case "WATCH":
                return Watch.from_json(data)
            case "SKY":
                return Sky.from_json(data)
            case "POLL":
                return Poll.from_json(data)
            case "GST":
                return GST.from_json(data)
            case "ERROR":
                error = Error.from_json(data)
                raise ValueError(f"Error: {error.message}")
            case _:
                raise ValueError(f"Unknown type: {data.get('class')}")

    async def recv(self):
        data = await self.__read()
        result = self.__class_factory(data)
        if isinstance(result, Version):
            self._version = result
        if isinstance(result, Devices):
            self._devices = result
        if isinstance(result, Watch):
            self._watch = result
        return result

    async def watch(self):
        wd = asdict(self.watch_config)
        self.__writer.write(WATCH.format(json.dumps(wd)).encode())
        await self.__writer.drain()

    async def poll(self):
        self.__writer.write(POLL.encode())
        await self.__writer.drain()
        return await self.recv()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    def __aiter__(self):
        return self

    async def __anext__(self):
        """
        Asynchronous iterator method that returns the next item from the iterator.

        Returns:
            The next item from the iterator.
        """
        return await self.recv()


async def open(host: str = "127.0.0.1", port: int = 2947) -> Client:
    reader, writer = await asyncio.open_connection(host, port)
    client = Client(reader, writer)
    await client.watch()
    return client
