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


async def invoke(
    callables: set, input: str | dict
) -> JSONRPCResponse | JSONRPCError | None:
    try:
        data = input
        if isinstance(input, str):
            data = json.loads(input)

        if "method" not in data or "params" not in data:
            return JSONRPCError(0, -32600, "Invalid Request")

        request = JSONRPCRequest(**data)
        if request.jsonrpc != "2.0":
            return JSONRPCError(request.id, -32600, "Invalid Request")

        for callable in callables:
            if request.method.lower() == callable.__name__:
                if asyncio.iscoroutinefunction(callable):
                    result = await callable(*request.params)
                else:
                    result = callable(*request.params)
                if request.id is None:
                    return
                response = JSONRPCResponse(result, request.id)
                return response

        return JSONRPCError(request.id, -32601, "Method not found")

    except json.JSONDecodeError:
        return JSONRPCError(0, -32700, "Parse error")
    except TypeError:
        return JSONRPCError(0, -32602, "Invalid params")
    except Exception:
        return JSONRPCError(0, -32603, "Internal error")

