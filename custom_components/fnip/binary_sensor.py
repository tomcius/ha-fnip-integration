"""Binary sensor platform for FutureNow FNIP — physical input channels.

This is the capability neither the core HA `futurenow` integration nor the
legacy fn_relay/fn_io/fn_dimmer components exposed generically: reading the
state of every input channel on every module type, not just outputs.
"""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CHANNELS, CONF_INPUTS, CONF_NAME, DOMAIN
from .entity import FnipChannelEntity
from .fnip.client import FNIPClient


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client: FNIPClient = hass.data[DOMAIN][entry.entry_id]
    inputs = entry.data[CONF_CHANNELS][CONF_INPUTS]

    entities = [
        FnipBinarySensor(client, entry, channel, cfg[CONF_NAME])
        for channel, cfg in inputs.items()
    ]
    async_add_entities(entities)


class FnipBinarySensor(FnipChannelEntity, BinarySensorEntity):
    """A physical input channel (wall switch/button/contact) on a FNIP module.

    Named distinctly from its paired output entity (both otherwise share the
    channel's configured name, e.g. "Korytarz") so it reads unambiguously as
    the physical switch's state, not another control for the same light.
    """

    _attr_icon = "mdi:light-switch"

    def __init__(self, client: FNIPClient, entry: ConfigEntry, channel: str, name: str) -> None:
        super().__init__(client, entry, channel, f"{name} (wyłącznik ścienny)", "input")
        self._attr_is_on: bool | None = None

    async def async_added_to_hass(self) -> None:
        self._subscribe("IN", self._on_update)
        await self._client.query_inputs()

    def _on_update(self, value: int) -> None:
        self._attr_is_on = bool(value)
        self.async_write_ha_state()
