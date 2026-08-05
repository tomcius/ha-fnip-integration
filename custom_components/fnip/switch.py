"""Switch platform for FutureNow FNIP — relay outputs with role 'switch'."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CHANNELS, CONF_NAME, CONF_OUTPUTS, CONF_ROLE, DOMAIN, ROLE_SWITCH
from .entity import FnipChannelEntity
from .fnip.client import FNIPClient


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client: FNIPClient = hass.data[DOMAIN][entry.entry_id]
    outputs = entry.data[CONF_CHANNELS][CONF_OUTPUTS]

    entities = [
        FnipSwitch(client, entry, channel, cfg[CONF_NAME])
        for channel, cfg in outputs.items()
        if cfg[CONF_ROLE] == ROLE_SWITCH
    ]
    async_add_entities(entities)


class FnipSwitch(FnipChannelEntity, SwitchEntity):
    """A relay output exposed as a switch (default role for REL/IO outputs)."""

    def __init__(self, client: FNIPClient, entry: ConfigEntry, channel: str, name: str) -> None:
        super().__init__(client, entry, channel, name, "output")
        self._attr_is_on = False

    async def async_added_to_hass(self) -> None:
        self._subscribe("OUT", self._on_update)
        await self._client.query_outputs()

    def _on_update(self, value: int) -> None:
        self._attr_is_on = bool(value)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.send_command("ON", self._channel)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.send_command("OFF", self._channel)
