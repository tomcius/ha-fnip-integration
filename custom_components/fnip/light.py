"""Light platform for FutureNow FNIP — plain relay lights and DIM/PWM dimmers."""
from __future__ import annotations

import time
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CHANNELS,
    CONF_MODULE_TYPE,
    CONF_NAME,
    CONF_OUTPUTS,
    CONF_ROLE,
    DOMAIN,
    MODULE_TYPES,
    ROLE_LIGHT,
)
from .entity import FnipChannelEntity
from .fnip.client import FNIPClient


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client: FNIPClient = hass.data[DOMAIN][entry.entry_id]
    spec = MODULE_TYPES[entry.data[CONF_MODULE_TYPE]]
    outputs = entry.data[CONF_CHANNELS][CONF_OUTPUTS]

    entities: list[LightEntity] = []
    for channel, cfg in outputs.items():
        if cfg[CONF_ROLE] != ROLE_LIGHT:
            continue
        if spec.level_scale is not None:
            entities.append(FnipDimmerLight(client, entry, channel, cfg[CONF_NAME], spec.level_scale))
        else:
            entities.append(FnipRelayLight(client, entry, channel, cfg[CONF_NAME]))

    async_add_entities(entities)


class FnipRelayLight(FnipChannelEntity, LightEntity):
    """A plain on/off relay output exposed as a light (user-chosen role)."""

    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

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


class FnipDimmerLight(FnipChannelEntity, LightEntity):
    """A DIM (0-100) or PWM (0-255) dimmer channel with brightness support.

    LEV,ch,0 (or any LEV target) triggers a hardware ramp, not an instant
    jump — the module sends step-by-step FN,LEV,ch,<intermediate> pushes
    while fading (see CLAUDE.md "FNIP-6x2AD ... During ramping, module
    sends step-by-step FN,LEV,ch,level notifications"). Taken at face
    value, an intermediate push during a commanded turn_off still reports
    brightness > 0, which would flip is_on back to True mid-fade — visible
    in the UI as the toggle bouncing to on right after being switched off.
    _RAMP_SETTLE_S suppresses is_on updates from push data for a short
    window after a locally issued command so the optimistic target state
    sticks through the fade; brightness itself keeps updating live so the
    fade is still visible wherever a slider is shown.
    """

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _RAMP_SETTLE_S = 3.0

    def __init__(
        self, client: FNIPClient, entry: ConfigEntry, channel: str, name: str, level_scale: int
    ) -> None:
        super().__init__(client, entry, channel, name, "output")
        self._level_scale = level_scale
        self._attr_brightness = 0
        self._attr_is_on = False
        self._ignore_is_on_until = 0.0

    async def async_added_to_hass(self) -> None:
        self._subscribe("LEV", self._on_level)
        self._subscribe("OUT_STOP", self._on_level)
        await self._client.query_outputs()

    def _on_level(self, value: int) -> None:
        self._attr_brightness = round(value / self._level_scale * 255)
        if time.monotonic() >= self._ignore_is_on_until:
            self._attr_is_on = value > 0
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness or 255)
        level = round(brightness / 255 * self._level_scale)
        self._attr_is_on = True
        self._attr_brightness = brightness
        self._ignore_is_on_until = time.monotonic() + self._RAMP_SETTLE_S
        self.async_write_ha_state()
        await self._client.send_command("LEV", self._channel, str(level))

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self._attr_brightness = 0
        self._ignore_is_on_until = time.monotonic() + self._RAMP_SETTLE_S
        self.async_write_ha_state()
        await self._client.send_command("LEV", self._channel, "0")
