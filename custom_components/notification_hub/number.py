"""Regler: Lautstärke kritischer Benachrichtigungen pro Gerät."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, STATE_UNAVAILABLE, STATE_UNKNOWN, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import NotificationHubConfigEntry
from .const import DOMAIN
from .hub import NotificationHub, Target


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NotificationHubConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Pro Gerät der Home-Assistant-App einen Lautstärke-Regler anlegen."""
    hub = entry.runtime_data
    async_add_entities(
        CriticalVolumeNumber(hub, target) for target in hub.async_get_targets().values()
    )


class CriticalVolumeNumber(NumberEntity, RestoreEntity):
    """Lautstärke, mit der kritische Benachrichtigungen auf diesem Gerät klingeln."""

    _attr_has_entity_name = True
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 5
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:volume-high"

    def __init__(self, hub: NotificationHub, target: Target) -> None:
        self.hub = hub
        self._device_id = target.device_id
        entry_id = hub.entry.entry_id
        self._attr_unique_id = f"{entry_id}_{target.app_device_id}_critical_volume"
        self._attr_name = f"Kritische Lautstärke {target.name}"
        # Gerät wird in devices.py angelegt, hier nur verknüpfen
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)})
        self._attr_extra_state_attributes = {"device_id": target.device_id}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        state = await self.async_get_last_state()
        if state is not None and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self.hub.critical_volumes[self._device_id] = float(state.state)
            except ValueError:
                pass

    @property
    def native_value(self) -> float:
        return self.hub.critical_volume(self._device_id)

    async def async_set_native_value(self, value: float) -> None:
        self.hub.critical_volumes[self._device_id] = float(value)
        self.async_write_ha_state()
