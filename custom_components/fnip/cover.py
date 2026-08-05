"""Cover platform for FutureNow FNIP — FNIP-4xSH shade/blind channels.

New relative to the legacy fn_relay-style components, which had no cover
support at all. Position semantics (GOTO/STOP, 0-100) mirror the dimmer LEV
pattern per fnip_mcp_server's README/CLAUDE.md — largely unverified beyond
test_device.py's basic UP/STOP/GOTO smoke test, so treat as v1/best-effort.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverDeviceClass, CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CHANNELS, CONF_MODULE_TYPE, CONF_NAME, CONF_OUTPUTS, DOMAIN, TYPE_SH
from .entity import FnipChannelEntity
from .fnip.client import FNIPClient


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data[CONF_MODULE_TYPE] != TYPE_SH:
        return

    client: FNIPClient = hass.data[DOMAIN][entry.entry_id]
    outputs = entry.data[CONF_CHANNELS][CONF_OUTPUTS]

    entities = [
        FnipCover(client, entry, channel, cfg[CONF_NAME]) for channel, cfg in outputs.items()
    ]
    async_add_entities(entities)


class FnipCover(FnipChannelEntity, CoverEntity):
    """A FNIP-4xSH shade channel: 0 = fully closed, 100 = fully open."""

    _attr_device_class = CoverDeviceClass.SHADE
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, client: FNIPClient, entry: ConfigEntry, channel: str, name: str) -> None:
        super().__init__(client, entry, channel, name, "output")
        self._attr_current_cover_position: int | None = None

    async def async_added_to_hass(self) -> None:
        self._subscribe("LEV", self._on_level)
        self._subscribe("OUT_STOP", self._on_level)
        await self._client.query_outputs()

    def _on_level(self, value: int) -> None:
        self._attr_current_cover_position = value
        self.async_write_ha_state()

    @property
    def is_closed(self) -> bool | None:
        if self._attr_current_cover_position is None:
            return None
        return self._attr_current_cover_position <= 0

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._client.send_command("UP", self._channel)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._client.send_command("DOWN", self._channel)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._client.send_command("STOP", self._channel)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs["position"]
        await self._client.send_command("GOTO", self._channel, str(position))
