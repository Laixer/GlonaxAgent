import argparse
import asyncio
import websockets
import logging
import time

from aiortc import RTCIceCandidate, RTCPeerConnection, RTCSessionDescription


async def consume_signaling(pc, signaling):
    while True:
        obj = await signaling.receive()

        if isinstance(obj, RTCSessionDescription):
            await pc.setRemoteDescription(obj)

            if obj.type == "offer":
                # send answer
                await pc.setLocalDescription(await pc.createAnswer())
                await signaling.send(pc.localDescription)
        elif isinstance(obj, RTCIceCandidate):
            await pc.addIceCandidate(obj)
        elif obj is BYE:
            print("Exiting")
            break


time_start = None


def current_stamp():
    global time_start

    if time_start is None:
        time_start = time.time()
        return 0
    else:
        return int((time.time() - time_start) * 1000000)


async def run_offer(pc, signaling):
    await signaling.connect()

    channel = pc.createDataChannel("chat")
    print("created by local party")

    async def send_pings():
        while True:
            channel.send("ping %d" % current_stamp())
            await asyncio.sleep(1)

    @channel.on("open")
    def on_open():
        asyncio.ensure_future(send_pings())

    @channel.on("message")
    def on_message(message):
        print("<", message)

        if isinstance(message, str) and message.startswith("pong"):
            elapsed_ms = (current_stamp() - int(message[5:])) / 1000
            print(" RTT %.2f ms" % elapsed_ms)

    await pc.setLocalDescription(await pc.createOffer())
    await signaling.send(pc.localDescription)

    await consume_signaling(pc, signaling)


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser(description="Data channels ping/pong")
#     parser.add_argument("role", choices=["offer", "answer"])
#     parser.add_argument("--verbose", "-v", action="count")
#     args = parser.parse_args()

#     if args.verbose:
#         logging.basicConfig(level=logging.DEBUG)

#     # signaling = create_signaling(args)
#     pc = RTCPeerConnection()
#     coro = run_offer(pc, signaling)

#     # run event loop
#     loop = asyncio.get_event_loop()
#     try:
#         asyncio.create_task(coro)
#     except KeyboardInterrupt:
#         pass
#     finally:
#         loop.run_until_complete(pc.close())
#         loop.run_until_complete(signaling.close())

import json
from jsonrpc import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
)


class RPCProxy:
    def __init__(self, uri: str):
        self.uri = uri

    async def __aenter__(self):
        self.websocket = await websockets.connect(self.uri)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.websocket.close()

    async def _remote_call(self, method: str, *args):
        req = JSONRPCRequest(id=1, method=method, params=args)

        await self.websocket.send(req.json())
        resp = json.loads(await self.websocket.recv())
        if "error" in resp:
            # response = JSONRPCError(**resp)
            print(resp)
            raise Exception(
                f"Received error from the server: {resp['error']['message']}"
            )
        else:
            response = JSONRPCResponse(**resp)
            return response.result


class GlonaxRPC(RPCProxy):
    async def echo(self, message: str) -> str:
        return await self._remote_call("echo", message)

    # async def glonax_instance(self):
    #     return await self._remote_call("glonax_instance")

    async def apt(self, operation: str, package: str):
        await self._remote_call("apt", operation, package)


async def main():
    uri = "wss://edge.laixer.equipment/api/app/d6d1a2db-52b9-4abb-8bea-f2d0537432e2/ws"

    proxy = GlonaxRPC(uri)
    async with proxy as rpc:
        # print(await rpc.echo("Hello, World", 435))
        # print(await rpc.glonax_instance())
        await rpc.apt("upgrade", "-")


if __name__ == "__main__":
    asyncio.run(main())
