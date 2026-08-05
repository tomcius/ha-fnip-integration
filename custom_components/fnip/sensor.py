"""Sensor platform for FutureNow FNIP — analog resistance on FNIP-12xIO inputs.

FNIP-12xIO inputs use resistive detection and report a raw resistance value
(FN,VAL,ch,value, units 0.1 kOhm) in addition to the ON/OFF binary_sensor —
see CLAUDE.md "FNIP-12xIO specifics". Only created for module_type == IO.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CHANNELS, CONF_INPUTS, CONF_MODULE_TYPE, CONF_NAME, DOMAIN, TYPE_IO
from .entity import FnipChannelEntity
from .fnip.client import FNIPClient


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data[CONF_MODULE_TYPE] != TYPE_IO:
        return

    client: FNIPClient = hass.data[DOMAIN][entry.entry_id]
    inputs = entry.data[CONF_CHANNELS][CONF_INPUTS]

    entities = [
        FnipResistanceSensor(client, entry, channel, cfg[CONF_NAME])
        for channel, cfg in inputs.items()
    ]
    async_add_entities(entities)


class FnipResistanceSensor(FnipChannelEntity, SensorEntity):
    """Raw input resistance (0.1 kOhm units) for a FNIP-12xIO input channel."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "kOhm"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, client: FNIPClient, entry: ConfigEntry, channel: str, name: str) -> None:
        super().__init__(client, entry, channel, f"{name} resistance", "input_resistance")
        self._attr_native_value: float | None = None

    async def async_added_to_hass(self) -> None:
        self._subscribe("VAL", self._on_update)
        await self._client.query_inputs()

    def _on_update(self, value: int) -> None:
        self._attr_native_value = round(value * 0.1, 1)
        self.async_write_ha_state()
