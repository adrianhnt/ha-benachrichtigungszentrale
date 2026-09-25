"""Sensor: zuletzt gesendete Benachrichtigung."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import NotificationHubConfigEntry
from .const import DOMAIN, SIGNAL_SENT
from .hub import NotificationHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NotificationHubConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Sensor anlegen."""
    async_add_entities([LastNotificationSensor(entry.runtime_data)])


class LastNotificationSensor(SensorEntity):
    """Zeitpunkt und Inhalt der zuletzt gesendeten Benachrichtigung."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_notification"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, hub: NotificationHub) -> None:
        self.hub = hub
        entry_id = hub.entry.entry_id
        self._attr_unique_id = f"{entry_id}_last_notification"
        # Gerät wird in devices.py angelegt, hier nur verknüpfen
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_SENT, self._updated)
        )

    @callback
    def _updated(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> datetime | None:
        return self.hub.last_sent["sent_at"] if self.hub.last_sent else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if not self.hub.last_sent:
            return None
        return {k: v for k, v in self.hub.last_sent.items() if k != "sent_at"}
