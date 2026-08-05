"""Light platform for FutureNow FNIP — plain relay lights and DIM/PWM dimmers."""
from __future__ import annotations

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

    LEV,ch,<target> triggers a hardware ramp, not an instant jump — the
    module brackets it with FN,OUT,START,ch (ramp begins) ... a burst of
    step-by-step FN,LEV,ch,<intermediate> pushes while fading ... FN,OUT,
    STOP,ch,<level> (ramp genuinely finished, with the settled level) —
    see CLAUDE.md "FNIP-6x2AD ... During ramping...". is_on is therefore
    only taken from LEV while NOT inside a START..STOP bracket (that
    covers the plain single-shot LEV a fresh SRE query returns) or from
    the final OUT_STOP once the ramp completes — never from an
    in-flight intermediate step. This tracks protocol-confirmed
    completion rather than a guessed timeout, so it stays correct
    regardless of how long the module's configured ramp duration is.
    Brightness still updates on every push so a slider shows the live fade.
    """

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(
        self, client: FNIPClient, entry: ConfigEntry, channel: str, name: str, level_scale: int
    ) -> None:
        super().__init__(client, entry, channel, name, "output")
        self._level_scale = level_scale
        self._attr_brightness = 0
        self._attr_is_on = False
        self._ramping = False

    async def async_added_to_hass(self) -> None:
        self._subscribe("OUT_START", self._on_ramp_start)
        self._subscribe("LEV", self._on_level)
        self._subscribe("OUT_STOP", self._on_ramp_stop)
        await self._client.query_outputs()

    def _on_ramp_start(self, value: int) -> None:
        self._ramping = True

    def _on_level(self, value: int) -> None:
        self._attr_brightness = round(value / self._level_scale * 255)
        if not self._ramping:
            # Not bracketed by OUT_START/OUT_STOP — a plain status report
            # (e.g. the single LEV reply to a fresh SRE query), trust it directly.
            self._attr_is_on = value > 0
        self.async_write_ha_state()

    def _on_ramp_stop(self, value: int) -> None:
        self._ramping = False
        self._attr_brightness = round(value / self._level_scale * 255)
        self._attr_is_on = value > 0
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness or 255)
        level = round(brightness / 255 * self._level_scale)
        await self._client.send_command("LEV", self._channel, str(level))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.send_command("LEV", self._channel, "0")
