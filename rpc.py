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


# {
#   "jsonrpc": "2.0",
#   "error": {
#     "code": -32600,
#     "message": "Invalid Request"
#   },
#   "id": 1
# }


class JSONRPCError:
    def __init__(self, id: int, code: int, message: str, jsonrpc: str = "2.0"):
        self.code = code
        self.message = message
        self.id = id
        self.jsonrpc = jsonrpc

    def json(self):
        return json.dumps(self.__dict__)


async def handle(callables: list, input: str | dict) -> str | None:
    try:
        data = input
        if isinstance(input, str):
            data = json.loads(input)

        request = JSONRPCRequest(**data)
        if request.jsonrpc != "2.0":
            return JSONRPCError(request.id, -32600, "Invalid Request").json()

        for callable in callables:
            if request.method.lower() == callable.__name__:
                if asyncio.iscoroutinefunction(callable):
                    result = await callable(*request.params)
                else:
                    result = callable(*request.params)
                if request.id is None:
                    return
                response = JSONRPCResponse(result, request.id)
                return response.json()

        return JSONRPCError(request.id, -32601, "Method not found").json()

    except json.JSONDecodeError:
        return JSONRPCError(0, -32700, "Parse error").json()
    except TypeError:
        return JSONRPCError(0, -32602, "Invalid params").json()
    except Exception:
        return JSONRPCError(0, -32603, "Internal error").json()

