import asyncio
import json
from dataclasses import asdict

from gps.schemas import TPV, Device, Devices, Response, Sky, Version, Watch, Poll

POLL = "?POLL;\r\n"
WATCH = "?WATCH={}\r\n"


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

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

        wd = asdict(self.watch_config)

        self.writer.write(WATCH.format(json.dumps(wd)).encode())
        await self.writer.drain()

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()

    @staticmethod
    def __class_factory(data):
        class_type = data.get("class").upper()
        excluded_keys = ["class"]
        filtered_data = {k: v for k, v in data.items() if k not in excluded_keys}

        if class_type == "TPV":
            return TPV(**filtered_data)
        elif class_type == "VERSION":
            return Version(**filtered_data)
        elif class_type == "DEVICES":
            return Devices(**filtered_data)
        elif class_type == "DEVICE":
            return Device(**filtered_data)
        elif class_type == "WATCH":
            return Watch(**filtered_data)
        elif class_type == "SKY":
            return Sky(**filtered_data)
        elif class_type == "POLL":
            return Poll(**filtered_data)
        else:
            print("Unknown class:", data)
            raise ValueError(f"Unknown type: {data.get('class')}")

    async def get_result(self):
        try:
            resp = await self.reader.readline()
            data = json.loads(resp)

            result = self.__class_factory(data)
            if isinstance(result, Version):
                self.version = result
            if isinstance(result, Devices):
                self.devices = result
            if isinstance(result, Watch):
                self.watch = result

            return result
        except json.JSONDecodeError:
            print("Invalid JSON data")
        except ValueError as e:
            print(f"Error creating object: {e}")

    async def poll(self):
        self.writer.write(POLL.encode())
        await self.writer.drain()
        return await self.get_result()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()
