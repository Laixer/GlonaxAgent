import json
import asyncio
import logging
from typing import Callable
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)


@dataclass
class JSONRPCRequest:
    """
    Represents a JSON-RPC request.

    Attributes:
        method (str): The name of the method to be called.
        params (any): The parameters to be passed to the method.
        id (int | None, optional): The request ID. Defaults to None.
        jsonrpc (str, optional): The JSON-RPC version. Defaults to "2.0".
    """

    method: str
    params: any
    id: int | None = None
    jsonrpc: str = "2.0"

    def json(self):
        """
        Returns the JSON representation of the request.

        Returns:
            str: The JSON representation of the request.
        """
        return json.dumps(asdict(self))


@dataclass
class JSONRPCResponse:
    """
    Represents a JSON-RPC response object.

    Attributes:
        result (any): The result of the JSON-RPC method call.
        id (int): The unique identifier of the JSON-RPC request.
        jsonrpc (str): The version of the JSON-RPC protocol (default: "2.0").
    """

    result: any
    id: int
    jsonrpc: str = "2.0"

    def json(self):
        """
        Returns the JSON representation of the JSON-RPC response object.

        Returns:
            str: The JSON representation of the response object.
        """
        return json.dumps(asdict(self))


@dataclass
class JSONRPCError:
    """
    Represents a JSON-RPC error object.

    Attributes:
        id (int): The unique identifier of the JSON-RPC request.
        code (int): The error code.
        message (str): The error message.
        jsonrpc (str): The version of the JSON-RPC protocol (default: "2.0").
    """

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
        """
        Returns the JSON representation of the JSON-RPC response object.

        Returns:
            str: The JSON representation of the response object.
        """
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
    """
    Invokes the appropriate callable function based on the JSON-RPC request.

    Args:
        callables (set[Callable]): A set of callable functions to be invoked.
        input (str | dict | list): The JSON-RPC request input.
        prefix (str, optional): The prefix to be added to the method name when matching callable functions. Defaults to "rpc_".

    Returns:
        JSONRPCResponse | JSONRPCError | None: The JSON-RPC response or error, or None if the request has no id.
    """
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
