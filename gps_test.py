import asyncio


async def main():
    from gps import client

    HOST = "127.0.0.1"
    PORT = 2947

    async with client.GpsdClient(HOST, PORT) as client:
        print(await client.poll())  # Get gpsd POLL response
        while True:
            print("")
            print(await client.get_result())  # Get gpsd TPV responses


if __name__ == "__main__":
    asyncio.run(main())
