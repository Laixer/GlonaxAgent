import asyncio

# from gps.exceptions import GpsdClientError
from gps.schemas import TPV, Devices, Response, Sky, Version, Watch

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

    def __getattr__(self, item):
        if item in ("reader", "writer"):
            # raise GpsdClientError("Initiate connection with client.connect()")
            raise AttributeError(item)
        raise AttributeError(item)

    async def connect(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)

        self.writer.write(
            WATCH.format(
                self.watch_config.model_dump_json(by_alias=True, exclude={"class_"})
            ).encode()
        )
        await self.writer.drain()

        self.version = await self.get_result()
        self.devices = await self.get_result()
        self.watch = await self.get_result()

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()

    async def get_result(self):
        # return Response.parse_raw(await self.reader.readline()).__root__
        return Response.model_validate_json(await self.reader.readline())

    async def poll(self):
        self.writer.write(POLL.encode())
        await self.writer.drain()
        return await self.get_result()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    def __aiter__(self):
        return self

    async def __anext__(self):
        result = await self.get_result()
        if isinstance(result, TPV):
            return result
        if isinstance(result, Sky):
            self.sky = result
        return await anext(self)
