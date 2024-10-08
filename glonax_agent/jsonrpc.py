import json
import asyncio
import logging
import inspect
import dataclasses
from typing import Callable, get_type_hints
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)


class JSONRPCRuntimeError(RuntimeError):
    """Exception raised for JSON-RPC runtime errors.

    This exception is raised when there is a runtime error in the JSON-RPC communication.

    Attributes:
        message -- explanation of the error
    """

    pass


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


class JSONRPCInternalError(JSONRPCError):
    def __init__(self, id: int):
        super().__init__(id, -32603, message="Internal error", jsonrpc="2.0")


async def invoke(
    callables: set[Callable],
    input: str | dict | list,
    prefix: str = "rpc_",
    auth_callback: Callable = None,
) -> JSONRPCResponse | JSONRPCError | None:
    """
    Invokes the appropriate callable function based on the JSON-RPC request.

    Args:
        callables (set[Callable]): A set of callable functions to be invoked.
        input (str | dict | list): The JSON-RPC request input.
        prefix (str, optional): The prefix to be added to the method name when matching callable functions. Defaults to "rpc_".
        auth_callback (Callable, optional): The authentication callback function. Defaults to None.

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

        if "auth" in data and auth_callback:
            if not auth_callback(data["auth"]):
                return JSONRPCError(data.get("id", None), 32000, "Unauthorized")

        def map_to_dataclass(params: list[dict], callable: Callable) -> list:
            type_hints = get_type_hints(callable)

            param_results = []

            sig = inspect.signature(callable)
            for param, (param_name, _) in zip(params, sig.parameters.items()):
                param_type = type_hints.get(param_name, None)
                if dataclasses.is_dataclass(param_type):
                    param_results.append(param_type(**param))

            return param_results

        request = JSONRPCRequest(**data)
        for callable in callables:
            method = request.method.strip()
            if method == callable.__name__ or prefix + method == callable.__name__:
                if asyncio.iscoroutinefunction(callable):
                    # TODO: Move into a separate function
                    if isinstance(request.params, dict):
                        param_results = map_to_dataclass([request.params], callable)
                        if param_results:
                            result = await callable(*param_results)
                        else:
                            result = await callable(**request.params)
                    elif isinstance(request.params, list):
                        if all(isinstance(param, dict) for param in request.params):
                            param_results = map_to_dataclass(request.params, callable)
                            result = await callable(*param_results)
                        else:
                            result = await callable(*request.params)
                    else:
                        result = await callable(*request.params)

                else:
                    # TODO: Move into a separate function
                    if isinstance(request.params, dict):
                        param_results = map_to_dataclass([request.params], callable)
                        if param_results:
                            result = callable(*param_results)
                        else:
                            result = callable(**request.params)
                    elif isinstance(request.params, list):
                        if all(isinstance(param, dict) for param in request.params):
                            print("Params are list of dicts")
                            param_results = map_to_dataclass(request.params, callable)
                            result = callable(*param_results)
                        else:
                            result = callable(*request.params)
                    else:
                        result = callable(*request.params)

                if request.id is None:
                    return
                return JSONRPCResponse(result, request.id)

        return JSONRPCMethodNotFound(request.id)

    except json.JSONDecodeError:
        logger.warning("JSON-RPC 2.0: JSON decode error")
        return JSONRPCParseError()
    except TypeError:
        logger.warning("JSON-RPC 2.0: Invalid params for method")
        return JSONRPCInvalidParams(data.get("id", None))
    except JSONRPCRuntimeError as e:
        logger.warning(f"JSON-RPC 2.0: Runtime error: {str(e)}")
        return JSONRPCError(data.get("id", None), 32000, str(e))
    except Exception as e:
        logger.error(f"Internal error: {str(e)}", exc_info=True)
        return JSONRPCInternalError(data.get("id", None))


class Dispatcher(set):
    """
    A class that represents a JSON-RPC dispatcher.

    The Dispatcher class is used to register and invoke JSON-RPC methods.

    Attributes:
        None

    Methods:
        rpc_call: Registers a JSON-RPC method.
        __call__: Invokes the registered JSON-RPC methods.

    """

    def rpc_call(self, func):
        """
        Registers a JSON-RPC method.

        Args:
            func: The JSON-RPC method to register.

        Returns:
            None

        """
        self.add(func)

    def __call__(
        self, input: str | dict | list
    ) -> JSONRPCResponse | JSONRPCError | None:
        """
        Invokes the registered JSON-RPC methods.

        Args:
            input: The JSON-RPC request input.

        Returns:
            JSONRPCResponse: The JSON-RPC response.
            JSONRPCError: The JSON-RPC error response.
            None: If no matching method is found.

        """
        return invoke(self, input)
