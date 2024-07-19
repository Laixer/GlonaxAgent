import asyncio


async def main():
    from gps import client

    HOST = "127.0.0.1"
    PORT = 2947

    async with client.GpsdClient(HOST, PORT) as client:
        async for result in client:
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
