import asyncio


async def main():
    from gps import client

    HOST = "127.0.0.1"
    PORT = 2947

    async with client.GpsdClient(HOST, PORT) as client:
        async for result in client:
            print("\n")
            print(result)
        # while True:
        #     await client.poll()
        #     await asyncio.sleep(1)
        # print("")
        # print(await client.get_result())  # Get gpsd TPV responses


if __name__ == "__main__":
    asyncio.run(main())
