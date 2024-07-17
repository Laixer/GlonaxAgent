import json
import asyncio
import logging
from typing import Callable
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)

# TODO: Rename module to jsonrpc


@dataclass
class JSONRPCRequest:
    method: str
    params: any
    id: int | None = None
    jsonrpc: str = "2.0"

    def json(self):
        return json.dumps(asdict(self))


@dataclass
class JSONRPCResponse:
    result: any
    id: int
    jsonrpc: str = "2.0"

    def json(self):
        return json.dumps(asdict(self))


@dataclass
class JSONRPCError:
    id: int
    code: int
    message: str
    jsonrpc: str = "2.0"

    def as_dict(self):
        return {
            "jsonrpc": self.jsonrpc,
            "error": {"code": self.code, "message": self.message},
            "id": self.id,
        }

    def json(self):
        return json.dumps(self.as_dict())


class JSONRPCInvalidRequest(JSONRPCError):
    def __init__(self, id: int):
        super().__init__(id, -32600, message="Invalid Request", jsonrpc="2.0")


class JSONRPCMethodNotFound(JSONRPCError):
    def __init__(self, id: int):
        super().__init__(id, -32601, message="Method not found", jsonrpc="2.0")


class JSONRPCParseError(JSONRPCError):
    def __init__(self):
        super().__init__(0, -32700, message="Parse error", jsonrpc="2.0")


class JSONRPCInvalidParams(JSONRPCError):
    def __init__(self, id: int):
        super().__init__(id, -32602, message="Invalid params", jsonrpc="2.0")


async def invoke(
    callables: set[Callable], input: str | dict | list, prefix: str = "rpc_"
) -> JSONRPCResponse | JSONRPCError | None:
    try:
        if isinstance(input, str):
            data = json.loads(input)
        else:
            data = input

        if isinstance(data, list):
            return [await invoke(callables, item, prefix) for item in data]

        if (
            not isinstance(data, dict)
            or "jsonrpc" not in data
            or "method" not in data
            or data["jsonrpc"] != "2.0"
        ):
            return JSONRPCInvalidRequest(data.get("id", None))

        request = JSONRPCRequest(**data)
        for callable in callables:
            method = request.method.strip()
            if method == callable.__name__ or prefix + method == callable.__name__:
                if asyncio.iscoroutinefunction(callable):
                    result = (
                        await callable(**request.params)
                        if isinstance(request.params, dict)
                        else await callable(*request.params)
                    )
                else:
                    result = (
                        callable(**request.params)
                        if isinstance(request.params, dict)
                        else callable(*request.params)
                    )

                if request.id is None:
                    return
                return JSONRPCResponse(result, request.id)

        return JSONRPCMethodNotFound(request.id)

    except json.JSONDecodeError:
        logger.error("JSON decode error", exc_info=True)
        return JSONRPCParseError()
    except TypeError:
        logger.error("Invalid params", exc_info=True)
        return JSONRPCInvalidParams(data.get("id", None))
    except Exception as e:
        logger.error(f"Internal error: {str(e)}", exc_info=True)
        return JSONRPCError(data.get("id", None), -32603, "Internal error")
