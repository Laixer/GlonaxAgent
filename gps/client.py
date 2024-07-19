import asyncio

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

        # def __class_factory(data):
        #     if data.get('type') == 'A':
        #         return A(**data)
        #     elif data.get('type') == 'B':
        #         return B(**data)
        #     else:
        #         raise ValueError(f"Unknown type: {data.get('type')}")

    async def get_result(self):
        import json

        try:
            resp = await self.reader.readline()
            data = json.loads(resp)
            class_type = data.get("class")

            excluded_keys = ["class"]
            filtered_data = {k: v for k, v in data.items() if k not in excluded_keys}

            if class_type == "TPV":
                return TPV(**filtered_data)

            # if cls == "VERSION":
            #     return Version.model_validate_json(resp)
            # elif cls == "DEVICES":
            #     return Devices.model_validate_json(resp)
            # elif cls == "DEVICE":
            #     return Device.model_validate_json(resp)
            # elif cls == "WATCH":
            #     return Watch.model_validate_json(resp)
            # elif cls == "TPV":
            #     return TPV.model_validate_json(resp)
            # elif cls == "SKY":
            #     return Sky.model_validate_json(resp)
            # elif cls == "POLL":
            #     return Poll.model_validate_json(resp)
            # else:
            #     print("Unknown class:", cls)
        except json.JSONDecodeError:
            print("Invalid JSON data")
        except ValueError as e:
            print(f"Error creating object: {e}")
        # except Exception as e:
        #     print(resp)
        #     raise e

        # return Response.model_validate_json(resp)

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
