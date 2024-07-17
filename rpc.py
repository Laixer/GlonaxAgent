import asyncio
import json


class JSONRPCRequest:
    def __init__(
        self, method: str, params, id: int | None = None, jsonrpc: str = "2.0"
    ):
        self.method = method
        self.params = params
        self.id = id
        self.jsonrpc = jsonrpc

    def json(self):
        return json.dumps(self.__dict__)


class JSONRPCResponse:
    def __init__(self, result, id: int, jsonrpc: str = "2.0"):
        self.result = result
        self.id = id
        self.jsonrpc = jsonrpc

    def json(self):
        return json.dumps(self.__dict__)


class JSONRPCError:
    def __init__(self, id: int, code: int, message: str, jsonrpc: str = "2.0"):
        self.code = code
        self.message = message
        self.id = id
        self.jsonrpc = jsonrpc

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
    callables: set, input: str | dict, prefix: str = "rpc_"
) -> JSONRPCResponse | JSONRPCError | None:
    try:
        data = input
        if isinstance(input, str):
            data = json.loads(input)

        if "method" not in data or "params" not in data or "jsonrpc" not in data:
            return JSONRPCInvalidRequest(0)

        request = JSONRPCRequest(**data)
        if request.jsonrpc != "2.0":
            return JSONRPCInvalidRequest(request.id)

        for callable in callables:
            method = request.method.strip()
            if method == callable.__name__ or prefix + method == callable.__name__:
                if asyncio.iscoroutinefunction(callable):
                    result = await callable(*request.params)
                else:
                    result = callable(*request.params)
                if request.id is None:
                    return
                response = JSONRPCResponse(result, request.id)
                return response

        return JSONRPCMethodNotFound(request.id)

    except json.JSONDecodeError:
        return JSONRPCParseError()
    except TypeError:
        return JSONRPCInvalidParams(0)
    except Exception:
        return JSONRPCError(0, -32603, "Internal error")
