"""The FutureNow FNIP integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .fnip.client import FNIPClient

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.COVER,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = FNIPClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        name=entry.entry_id,
        display_name=entry.title,
    )
    await client.start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = client

    async def _stop(_event) -> None:
        await client.stop()

    entry.async_on_unload(
        hass.bus.async_listen_once("homeassistant_stop", _stop)
    )
    # Options flow changes channel names/roles in entry.data — a full reload
    # is needed so a role change (e.g. switch -> light) moves the entity to
    # the correct platform instead of leaving a stale one behind.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        client: FNIPClient = hass.data[DOMAIN].pop(entry.entry_id)
        await client.stop()
    return unload_ok
