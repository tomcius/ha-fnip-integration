"""Config flow for the FutureNow FNIP integration."""
from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_CHANNELS,
    CONF_INPUTS,
    CONF_MAC,
    CONF_MODULE_TYPE,
    CONF_NAME,
    CONF_OUTPUTS,
    CONF_ROLE,
    DEFAULT_PORT,
    DOMAIN,
    MODULE_TYPES,
    ROLE_LIGHT,
    ROLE_SWITCH,
    detect_type_from_mtype,
)

_LOGGER = logging.getLogger(__name__)

_PROBE_TIMEOUT = 5.0


class CannotConnect(Exception):
    """Raised when the probe connection fails."""


async def _recv_until_prompt(reader: asyncio.StreamReader, prompts: int, timeout: float) -> str:
    """Read until `prompts` '>' characters seen or timeout — mirrors test_device.py."""
    buf = ""
    count = 0
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while count < prompts:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        try:
            chunk = await asyncio.wait_for(reader.read(4096), timeout=min(remaining, 0.5))
        except asyncio.TimeoutError:
            continue
        if not chunk:
            break
        text = chunk.decode("ascii", errors="replace")
        buf += text
        count += text.count(">")
    return buf


async def probe_module(host: str, port: int) -> tuple[str, str]:
    """Connect once, run GETMAC + GETMTYPE, return (mac, mtype_string).

    Adapted from fnip_mcp_server/test_device.py's query_info(), which is
    already proven against real FNIP-6x2AD and FNIP-12xIO hardware.

    GETMAC is documented for every FNIP module type and is required — if
    it doesn't come back, the module is unreachable/wrong host and we raise
    CannotConnect. GETMTYPE, however, is only documented for FNIP-6x2AD
    (confirmed against "FNIP Communication Protocol Rev23.04.2021.pdf" —
    REL/IO/SH/PWM/RGB&010 sections don't list it at all). Other module
    types simply don't answer it, so an empty mtype_string is a normal,
    expected result here, not an error — the caller falls back to asking
    the user to pick the type manually.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=_PROBE_TIMEOUT
        )
    except (OSError, asyncio.TimeoutError) as exc:
        raise CannotConnect from exc

    try:
        await _recv_until_prompt(reader, prompts=1, timeout=1.0)  # discard banner '>'

        writer.write(b"FN,GETMAC\r\n")
        await writer.drain()
        mac_raw = await _recv_until_prompt(reader, prompts=2, timeout=_PROBE_TIMEOUT)
        mac = ""
        for line in mac_raw.split("\r"):
            if "MAC" in line:
                mac = line.split(",")[-1].strip().strip(">").strip()

        if not mac:
            raise CannotConnect

        writer.write(b"FN,GETMTYPE\r\n")
        await writer.drain()
        mtype_raw = await _recv_until_prompt(reader, prompts=2, timeout=_PROBE_TIMEOUT)
        mtype = ""
        for line in mtype_raw.split("\r"):
            if "MTYPE" in line:
                mtype = line.split(",")[-1].strip().strip(">").strip()

        return mac, mtype
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            await writer.wait_closed()


def _default_channel_name(kind: str, ch: str) -> str:
    return f"{'Output' if kind == 'output' else 'Input'} {ch}"


def _build_channels_schema(module_type: str) -> vol.Schema:
    spec = MODULE_TYPES[module_type]
    fields: dict[Any, Any] = {}

    for ch in range(1, spec.n_outputs + 1):
        ch_s = str(ch)
        fields[vol.Optional(f"out_{ch_s}_name", default=_default_channel_name("output", ch_s))] = str
        if spec.output_domain is None:
            fields[vol.Optional(f"out_{ch_s}_role", default=ROLE_SWITCH)] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[ROLE_LIGHT, ROLE_SWITCH],
                    translation_key="channel_role",
                )
            )

    for ch in range(1, spec.n_inputs + 1):
        ch_s = str(ch)
        fields[vol.Optional(f"in_{ch_s}_name", default=_default_channel_name("input", ch_s))] = str

    return vol.Schema(fields)


def _parse_channels_input(module_type: str, user_input: dict[str, Any]) -> dict[str, Any]:
    spec = MODULE_TYPES[module_type]
    outputs: dict[str, dict[str, str]] = {}
    inputs: dict[str, dict[str, str]] = {}

    for ch in range(1, spec.n_outputs + 1):
        ch_s = str(ch)
        role = (
            user_input.get(f"out_{ch_s}_role", ROLE_SWITCH)
            if spec.output_domain is None
            else spec.output_domain
        )
        outputs[ch_s] = {
            CONF_ROLE: role,
            CONF_NAME: user_input.get(f"out_{ch_s}_name", _default_channel_name("output", ch_s)),
        }

    for ch in range(1, spec.n_inputs + 1):
        ch_s = str(ch)
        inputs[ch_s] = {
            CONF_NAME: user_input.get(f"in_{ch_s}_name", _default_channel_name("input", ch_s)),
        }

    return {CONF_OUTPUTS: outputs, CONF_INPUTS: inputs}


class FnipConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for FutureNow FNIP."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._mac: str | None = None
        self._module_type: str | None = None
        self._raw_mtype: str = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._port = user_input[CONF_PORT]
            try:
                mac, mtype_raw = await probe_module(self._host, self._port)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                self._mac = mac
                self._raw_mtype = mtype_raw
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()

                module_type = detect_type_from_mtype(mtype_raw) if mtype_raw else None
                if module_type is not None:
                    self._module_type = module_type
                    return await self.async_step_channels()

                if mtype_raw:
                    _LOGGER.warning(
                        "Unrecognised FNIP module type %r from %s:%s — "
                        "not in MODULE_TYPES (v1 scope: REL/IO/DIM/PWM/SH), "
                        "falling back to manual selection",
                        mtype_raw, self._host, self._port,
                    )
                else:
                    _LOGGER.info(
                        "%s:%s did not answer GETMTYPE (only FNIP-6x2AD "
                        "documents that command) — falling back to manual "
                        "module type selection",
                        self._host, self._port,
                    )
                return await self.async_step_select_type()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_select_type(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._module_type = user_input[CONF_MODULE_TYPE]
            return await self.async_step_channels()

        schema = vol.Schema(
            {
                vol.Required(CONF_MODULE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[spec.key for spec in MODULE_TYPES.values()],
                    )
                ),
            }
        )
        return self.async_show_form(
            step_id="select_type",
            data_schema=schema,
            description_placeholders={
                "mac": self._mac or "",
                "raw_mtype": self._raw_mtype or "(brak odpowiedzi na GETMTYPE)",
            },
        )

    async def async_step_channels(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        assert self._module_type is not None

        if user_input is not None:
            channels = _parse_channels_input(self._module_type, user_input)
            spec = MODULE_TYPES[self._module_type]
            title = f"{spec.label.split(' (')[0]} ({self._host})"
            return self.async_create_entry(
                title=title,
                data={
                    CONF_HOST: self._host,
                    CONF_PORT: self._port,
                    CONF_MAC: self._mac,
                    CONF_MODULE_TYPE: self._module_type,
                    CONF_CHANNELS: channels,
                },
            )

        schema = _build_channels_schema(self._module_type)
        return self.async_show_form(
            step_id="channels",
            data_schema=schema,
            description_placeholders={
                "module_type": MODULE_TYPES[self._module_type].label,
                "mac": self._mac or "",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        from .options_flow import FnipOptionsFlow

        return FnipOptionsFlow(config_entry)
