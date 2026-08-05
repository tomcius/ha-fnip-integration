"""Shared base entity for FutureNow FNIP channel entities."""
from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import CONF_MAC, CONF_MODULE_TYPE, DOMAIN
from .fnip.client import FNIPClient


class FnipChannelEntity(Entity):
    """Base for every entity backed by one FNIP module channel.

    Push-based: subscribes to the client's pub/sub in async_added_to_hass
    instead of polling (should_poll stays False everywhere).
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        client: FNIPClient,
        entry: ConfigEntry,
        channel: str,
        name: str,
        unique_suffix: str,
    ) -> None:
        self._client = client
        self._entry = entry
        self._channel = channel
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}_{channel}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_MAC])},
            name=entry.title,
            manufacturer="FutureNow",
            model=entry.data[CONF_MODULE_TYPE],
        )
        self._sub_ids: list[UUID] = []

    def _subscribe(self, command: str, callback: Callable[[int], None]) -> None:
        """Subscribe to push updates for this entity's channel and track the
        subscription so it can be cleaned up in async_will_remove_from_hass."""
        sub_id = self._client.subscribe(command, self._channel, callback, permanent=True)
        self._sub_ids.append(sub_id)

    async def async_will_remove_from_hass(self) -> None:
        for sub_id in self._sub_ids:
            self._client.unsubscribe(sub_id)
        self._sub_ids.clear()
