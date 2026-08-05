from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from .models import ChannelNames, ModuleState
from .protocol import FNMessage, build_command, parse_messages

_LOGGER = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 5       # seconds between heartbeat sends
QUEUE_TIMEOUT = 15           # seconds without messages before reconnect
RECONNECT_DELAY = 5          # seconds between reconnect attempts
RECV_SIZE = 4096


@dataclass
class _Subscriber:
    command: str
    channel: str
    callback: Callable[[int], None]
    permanent: bool


class FNIPClient:
    """Async TCP client for a single FNIP module."""

    def __init__(self, host: str, port: int, name: str, display_name: str = "", channel_names: ChannelNames | None = None) -> None:
        self.host = host
        self.port = port
        self.name = name
        self.display_name = display_name or name
        self.channel_names = channel_names or ChannelNames()
        self.state = ModuleState()
        self._subscribers: dict[uuid.UUID, _Subscriber] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        await self._connect()
        self._tasks = [
            asyncio.create_task(self._reader_loop(), name=f"{self.name}-reader"),
            asyncio.create_task(self._dispatcher_loop(), name=f"{self.name}-dispatcher"),
            asyncio.create_task(self._heartbeat_loop(), name=f"{self.name}-heartbeat"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        _LOGGER.info("%s: stopped", self.name)

    def subscribe(self, command: str, channel: str, callback: Callable[[int], None], permanent: bool = True) -> uuid.UUID:
        sub_id = uuid.uuid4()
        self._subscribers[sub_id] = _Subscriber(command, channel, callback, permanent)
        _LOGGER.debug("%s: subscribed %s/%s", self.name, command, channel)
        return sub_id

    def unsubscribe(self, sub_id: uuid.UUID) -> None:
        self._subscribers.pop(sub_id, None)

    async def send_command(self, *parts: str) -> None:
        cmd = build_command(*parts)
        await self._send(cmd)

    async def query_outputs(self) -> None:
        await self._send("FN,SRE\r\n")

    async def query_inputs(self) -> None:
        await self._send("FN,SRI\r\n")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        while True:
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
                self._reader = reader
                self._writer = writer
                self._connected = True
                _LOGGER.info("%s: connected to %s:%d", self.name, self.host, self.port)
                await self.query_inputs()
                await self.query_outputs()
                return
            except OSError as exc:
                _LOGGER.warning("%s: connection failed (%s), retrying in %ds", self.name, exc, RECONNECT_DELAY)
                await asyncio.sleep(RECONNECT_DELAY)

    async def _send(self, data: str) -> None:
        if not self._connected or self._writer is None:
            _LOGGER.warning("%s: send skipped — not connected", self.name)
            return
        try:
            self._writer.write(data.encode("ascii"))
            await self._writer.drain()
            _LOGGER.debug("%s: sent %r", self.name, data.strip())
        except OSError as exc:
            _LOGGER.error("%s: send error: %s", self.name, exc)
            await self._reconnect()

    async def _reconnect(self) -> None:
        self._connected = False
        if self._writer:
            self._writer.close()
        _LOGGER.info("%s: reconnecting…", self.name)
        await self._connect()

    async def _reader_loop(self) -> None:
        while True:
            try:
                data = await self._reader.read(RECV_SIZE)
                if not data:
                    _LOGGER.warning("%s: server closed connection", self.name)
                    await self._reconnect()
                    continue
                text = data.decode("ascii", errors="replace")
                await self._queue.put(text)
            except asyncio.CancelledError:
                return
            except OSError as exc:
                _LOGGER.error("%s: reader error: %s", self.name, exc)
                await self._reconnect()

    async def _dispatcher_loop(self) -> None:
        while True:
            try:
                try:
                    raw = await asyncio.wait_for(self._queue.get(), timeout=QUEUE_TIMEOUT)
                except TimeoutError:
                    _LOGGER.debug("%s: no messages for %ds, reconnecting", self.name, QUEUE_TIMEOUT)
                    await self._reconnect()
                    continue

                for msg in parse_messages(raw):
                    self._update_state(msg)
                    self._notify_subscribers(msg)
                self._queue.task_done()
            except asyncio.CancelledError:
                return

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await self._send("a\r")
            except asyncio.CancelledError:
                return

    def _update_state(self, msg: FNMessage) -> None:
        if msg.command == "OUT":
            self.state.outputs[msg.channel] = bool(msg.value)
        elif msg.command == "IN":
            self.state.inputs[msg.channel] = bool(msg.value)
        elif msg.command == "VAL":
            self.state.analog_inputs[msg.channel] = msg.value
        elif msg.command in ("LEV", "OUT_STOP"):
            self.state.levels[msg.channel] = msg.value

    def _notify_subscribers(self, msg: FNMessage) -> None:
        to_remove: list[uuid.UUID] = []
        for sub_id, sub in list(self._subscribers.items()):
            if sub.command == msg.command and sub.channel == msg.channel:
                try:
                    sub.callback(msg.value)
                except Exception as exc:
                    _LOGGER.error("%s: subscriber callback error: %s", self.name, exc)
                if not sub.permanent:
                    to_remove.append(sub_id)
        for sub_id in to_remove:
            self.unsubscribe(sub_id)
