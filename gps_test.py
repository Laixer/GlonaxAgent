import asyncio


async def main():
    from gps import client

    HOST = "127.0.0.1"
    PORT = 2947

    async with await client.open(HOST, PORT) as c:
        async for result in c:
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
