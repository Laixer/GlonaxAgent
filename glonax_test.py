import asyncio

from aiochannel import ChannelClosed

from glonax import client as gclient
from glonax.client import Session
from glonax.message import (
    Control,
    ControlType,
    Message,
    ChannelMessageType,
    ModuleStatus,
    Motion,
    MotionChangeSet,
    MotionType,
    RTCSessionDescription,
)


async def main():
    path = "/tmp/glonax.sock"

    print("Connecting to Glonax")

    try:
        reader, writer = await gclient.open_unix_connection(path)

        async with Session(reader, writer) as session:
            await session.handshake()

            await asyncio.sleep(5)

            print("Sending motion")

            # m = Motion(
            #     type=MotionType.CHANGE,
            #     change=[
            #         MotionChangeSet(actuator=0, value=12_000),
            #         MotionChangeSet(actuator=1, value=-32_000),
            #         MotionChangeSet(actuator=4, value=2_000),
            #     ],
            # )

            m = Motion.straight_drive(1000)

            print(m.to_bytes())
            await session.writer.motion(m)

            # await session.writer.control(
            #     Control(type=0x2E, value=True)
            # )
    except asyncio.CancelledError:
        print("Glonax task cancelled")
        return
    except asyncio.IncompleteReadError as e:
        print("Glonax disconnected")
        await asyncio.sleep(1)
    except ConnectionError as e:
        print(f"Glonax connection error: {e}")
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
