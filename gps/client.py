import asyncio
import json
import logging
from dataclasses import asdict

from gps.schemas import TPV, Device, Devices, Sky, Version, Watch, Poll

POLL = "?POLL;\r\n"
WATCH = "?WATCH={}\r\n"

logger = logging.getLogger(__name__)


class GpsdClient:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    version: Version
    devices: Devices
    watch: Watch
    sky: Sky

    def __init__(
        self, host: str = "127.0.0.1", port: int = 2947, watch_config: Watch = Watch()
    ):
        self.host = host
        self.port = port

        self.watch_config = watch_config

    async def __read(self) -> dict:
        data = await self.__reader.readline()
        return json.loads(data)

    # TODO: Move out of class
    async def connect(self):
        self.__reader, self.__writer = await asyncio.open_connection(
            self.host, self.port
        )

        wd = asdict(self.watch_config)

        self.__writer.write(WATCH.format(json.dumps(wd)).encode())
        await self.__writer.drain()

    async def close(self):
        await self.__writer.drain()
        self.__writer.close()
        await self.__writer.wait_closed()

    @staticmethod
    def __class_factory(data: dict) -> object:
        class_type = data.get("class").upper()

        excluded_keys = ["class"]
        filtered_data = {k: v for k, v in data.items() if k not in excluded_keys}

        match class_type:
            case "TPV":
                return TPV(**filtered_data)
            case "VERSION":
                return Version(**filtered_data)
            case "DEVICES":
                return Devices(**filtered_data)
            case "DEVICE":
                return Device(**filtered_data)
            case "WATCH":
                return Watch(**filtered_data)
            case "SKY":
                return Sky(**filtered_data)
            case "POLL":
                return Poll(**filtered_data)
            case _:
                raise ValueError(f"Unknown type: {data.get('class')}")

    async def recv(self):
        data = await self.__read()
        try:
            result = self.__class_factory(data)
            if isinstance(result, Version):
                self.version = result
            if isinstance(result, Devices):
                self.devices = result
            if isinstance(result, Watch):
                self.watch = result
            return result
        except ValueError as e:
            print(f"Error creating object: {e}")

    async def poll(self):
        self.__writer.write(POLL.encode())
        await self.__writer.drain()
        return await self.recv()

    async def __aenter__(self):
        await self.connect()
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
