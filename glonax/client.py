import struct
import logging
import asyncio
from enum import Enum


logger = logging.getLogger(__name__)


class MachineType(Enum):
    EXCAVATOR = 1
    WHEEL_LOADER = 2
    DOZER = 3
    GRADER = 4
    HAULER = 5
    FORESTRY = 6

    def __str__(self):
        if self == MachineType.EXCAVATOR:
            return "excavator"
        elif self == MachineType.WHEEL_LOADER:
            return "wheel loader"
        elif self == MachineType.DOZER:
            return "dozer"
        elif self == MachineType.GRADER:
            return "grader"
        elif self == MachineType.HAULER:
            return "hauler"
        elif self == MachineType.FORESTRY:
            return "forestry"


class MessageType(Enum):
    ERROR = 0x00
    ECHO = 0x01
    SESSION = 0x10
    SHUTDOWN = 0x11
    REQUEST = 0x12
    INSTANCE = 0x15
    STATUS = 0x16
    MOTION = 0x20
    SIGNAL = 0x31
    ACTOR = 0x40
    VMS = 0x41  # TODO: Remove this message type
    GNSS = 0x42  # TODO: Remove this message type
    ENGINE = 0x43
    TARGET = 0x44
    CONTROL = 0x45
    ROTATOR = 0x46


class Packet:
    def to_bytes(self):
        pass

    def from_bytes(data):
        pass


class SessionFrame(Packet):
    def __init__(self, name):
        self.name = name

    def to_bytes(self):
        data = struct.pack("B", 3)
        data += self.name.encode("utf-8")

        return data

    def from_bytes(data):
        name = data[1:].decode("utf-8")
        return SessionFrame(name)


from glonax import DEFAULT_USER_AGENT
from glonax.message import (
    ChannelMessageType,
    Control,
    ControlType,
    Instance,
    Engine,
    Message,
    ModuleStatus,
    Motion,
)


class ProtocolError(Exception):
    pass


class GlonaxStreamWriter:
    def __init__(self, writer: asyncio.StreamWriter):
        self.writer = writer

    async def write(self, type: MessageType, data: bytes):
        header = b"LXR\x03"
        header += struct.pack("B", type.value)
        header += struct.pack(">H", len(data))
        header += b"\x00\x00\x00"
        self.writer.write(header + data)
        await self.writer.drain()

    async def motion(self, motion: Motion):
        await self.write(MessageType.MOTION, motion.to_bytes())

    async def control(self, control: Control):
        await self.write(MessageType.CONTROL, control.to_bytes())

    async def engine(self, engine: Engine):
        await self.write(MessageType.ENGINE, engine.to_bytes())


class GlonaxStreamReader:
    def __init__(self, reader: asyncio.StreamReader):
        self.reader = reader

    async def read(self) -> tuple[MessageType, bytes]:
        header = await self.reader.readexactly(10)
        if header[:3] != b"LXR":
            raise ProtocolError("Invalid header received")
        if header[3:4] != b"\x03":
            raise ProtocolError("Invalid protocol version")

        message_type = MessageType(struct.unpack("B", header[4:5])[0])
        message_length = struct.unpack(">H", header[5:7])[0]
        if header[7:10] != b"\x00\x00\x00":
            raise ProtocolError("Invalid header padding")
        message = await self.reader.readexactly(message_length)
        if len(message) != message_length:
            raise ProtocolError("Invalid message length")

        return message_type, message


# async def open_tcp_connection(
#     address: str = "localhost", port: int = 30051
# ) -> tuple[GlonaxStreamReader, GlonaxStreamWriter]:
#     reader, writer = await asyncio.open_connection(address, port)
#     reader = GlonaxStreamReader(reader)
#     writer = GlonaxStreamWriter(writer)
#     return reader, writer


async def open_unix_connection(
    path: str = "/tmp/glonax.sock",
) -> tuple[GlonaxStreamReader, GlonaxStreamWriter]:
    """
    Opens a Unix domain socket connection to the specified path.

    Args:
        path (str, optional): The path to the Unix domain socket. Defaults to "/tmp/glonax.sock".

    Returns:
        tuple[GlonaxStreamReader, GlonaxStreamWriter]: A tuple containing the reader and writer objects for the connection.

    Raises:
        ConnectionError: If the specified path does not exist.
    """
    try:
        reader, writer = await asyncio.open_unix_connection(path)
        reader = GlonaxStreamReader(reader)
        writer = GlonaxStreamWriter(writer)
        return reader, writer
    except FileNotFoundError as e:
        raise ConnectionError(f"Could not connect to {path}") from e


class Session:
    def __init__(
        self,
        reader: GlonaxStreamReader,
        writer: GlonaxStreamWriter,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.reader = reader
        self.writer = writer
        self.user_agent = user_agent

    async def close(self):
        """
        Closes the connection to the server.

        This method drains any pending data in the writer, closes the writer, and waits until the writer is fully closed.
        """
        await self.writer.writer.drain()
        self.writer.writer.close()
        await self.writer.writer.wait_closed()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """
        Clean up resources and close the client connection.

        Args:
            exc_type (type): The type of the exception raised, if any.
            exc_value (Exception): The exception raised, if any.
            traceback (traceback): The traceback object associated with the exception.

        Returns:
            None
        """
        await self.close()

    async def handshake(self):
        """
        Performs the handshake process with the Glonax server.

        This method sends a session message to the server and receives the response.
        If the response is an instance message, it sets the `machine` attribute of the client.

        Raises:
            SomeException: If an error occurs during the handshake process.
        """
        session = SessionFrame(self.user_agent)
        await self.writer.write(MessageType.SESSION, session.to_bytes())

        # TODO: Ask the reader to block until INSTANCE response is received
        message_type, message = await self.reader.read()
        if message_type == MessageType.INSTANCE:
            self.instance = Instance.from_bytes(message)
            logger.debug(f"Instance ID: {self.instance}")

    # TODO: See if we can reuse some of the methods from the `Session` class
    async def recv_message(self) -> Message | None:
        message_type, message = await self.reader.read()
        if message_type == MessageType.INSTANCE:
            instance = Instance.from_bytes(message)

            message = Message(
                type=ChannelMessageType.SIGNAL,
                topic="instance",
                payload=instance,
            )
            return message

        if message_type == MessageType.STATUS:
            status = ModuleStatus.from_bytes(message)

            message = Message(
                type=ChannelMessageType.SIGNAL,
                topic="status",
                payload=status,
            )
            return message

        elif message_type == MessageType.ENGINE:
            engine = Engine.from_bytes(message)

            message = Message(
                type=ChannelMessageType.SIGNAL,
                topic="engine",
                payload=engine,
            )
            return message
        elif message_type == MessageType.MOTION:
            motion = Motion.from_bytes(message)

            message = Message(
                type=ChannelMessageType.SIGNAL,
                topic="motion",
                payload=motion,
            )
            return message
        else:
            # TODO: Why not raise an exception here?
            return None

    async def machine_horn(self, value: bool):
        """
        Sends a control message to activate the machine horn.

        Args:
            value (bool): The value to set the machine horn.
        """
        await self.writer.control(Control(type=ControlType.MACHINE_HORN, value=value))

    async def machine_lights(self, value: bool):
        """
        Sends a control message to activate the machine lights.

        Args:
            value (bool): The value to set the machine lights.
        """
        await self.writer.control(Control(type=ControlType.MACHINE_LIGHTS, value=value))

    async def machine_illumination(self, value: bool):
        """
        Controls the machine illumination.

        Args:
            value (bool): The value to set for the machine illumination. True to turn on the illumination, False to turn it off.
        """
        await self.writer.control(
            Control(type=ControlType.MACHINE_ILLUMINATION, value=value)
        )

    async def machine_shutdown(self):
        """
        Sends a control message to shutdown the machine.
        """
        await self.writer.control(
            Control(type=ControlType.MACHINE_SHUTDOWN, value=True)
        )

    async def machine_strobe_light(self, value: bool):
        """
        Controls the machine strobe light.

        Args:
            value (bool): The value to set for the machine strobe light. True to turn on the strobe light, False to turn it off.
        """
        await self.writer.control(
            Control(type=ControlType.MACHINE_STROBE_LIGHT, value=value)
        )

    async def machine_travel_alarm(self, value: bool):
        """
        Controls the machine travel alarm.

        Args:
            value (bool): The value to set for the machine travel alarm. True to turn on the travel alarm, False to turn it off.
        """
        await self.writer.control(
            Control(type=ControlType.MACHINE_TRAVEL_ALARM, value=value)
        )

    async def hydraulic_lock(self, value: bool):
        """
        Controls the hydraulic lock of the Glonax client.

        Parameters:
        - value (bool): The value to set for the hydraulic lock. True to lock, False to unlock.

        Returns:
        - None

        Raises:
        - None
        """
        await self.writer.control(Control(type=ControlType.HYDRAULIC_LOCK, value=value))

    async def hydraulic_quick_disconnect(self, value: bool):
        """
        Controls the hydraulic quick disconnect feature.

        Parameters:
        - value (bool): The value to set for the hydraulic quick disconnect feature.

        Raises:
        - SomeException: If there is an error while controlling the hydraulic quick disconnect.

        Returns:
        - None
        """
        await self.writer.control(
            Control(type=ControlType.HYDRAULIC_QUICK_DISCONNECT, value=value)
        )

    async def hydraulic_boost(self, value: bool):
        """
        Controls the hydraulic boost feature.

        Parameters:
        - value (bool): The value to set for the hydraulic boost feature.

        Raises:
        - SomeException: If there is an error while controlling the hydraulic boost.

        Returns:
        - None
        """
        await self.writer.control(
            Control(type=ControlType.HYDRAULIC_BOOST, value=value)
        )

    async def hydraulic_boom_conflux(self, value: bool):
        """
        Sets the hydraulic boom conflux value.

        Args:
            value (bool): The value to set for hydraulic boom conflux.

        Raises:
            SomeException: If there is an error while setting the value.

        Returns:
            None
        """
        await self.writer.control(
            Control(type=ControlType.HYDRAULIC_BOOM_CONFLUX, value=value)
        )

    async def hydraulic_arm_conflux(self, value: bool):
        """
        Controls the hydraulic arm conflux.

        Parameters:
        - value (bool): The value to set for the hydraulic arm conflux.

        Returns:
        - None

        Raises:
        - None
        """
        await self.writer.control(
            Control(type=ControlType.HYDRAULIC_ARM_CONFLUX, value=value)
        )

    async def hydraulic_boom_float(self, value: bool):
        """
        Sets the hydraulic boom float state.

        Args:
            value (bool): The desired state of the hydraulic boom float.

        Raises:
            SomeException: If there is an error while setting the hydraulic boom float state.

        Returns:
            None
        """
        await self.writer.control(
            Control(type=ControlType.HYDRAULIC_BOOM_FLOAT, value=value)
        )

    async def engine_request(self, value: int):
        """
        Sends a request to the engine with the specified RPM value.

        Args:
            value (int): The RPM value to send to the engine.

        Returns:
            None
        """
        await self.writer.engine(Engine.request_rpm(value))

    async def engine_shutdown(self):
        """
        Shuts down the engine.

        This method sends a shutdown command to the engine and awaits its response.

        Returns:
            None
        """
        await self.writer.engine(Engine.shutdown())
