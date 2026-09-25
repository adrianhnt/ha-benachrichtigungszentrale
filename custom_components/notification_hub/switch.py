"""Schalter: Nicht stören (global) und Stumm (pro Benachrichtigungstyp)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import NotificationHubConfigEntry
from .const import CONF_KEY, CONF_TITLE, DOMAIN, SUBENTRY_TYPE
from .hub import NotificationHub


async def async_setup_entry(
    hass: HomeAssistant,
    entry: NotificationHubConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Schalter anlegen."""
    hub = entry.runtime_data
    async_add_entities([DoNotDisturbSwitch(hub)])

    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != SUBENTRY_TYPE:
            continue
        async_add_entities(
            [MuteSwitch(hub, subentry_id, subentry.data[CONF_KEY], subentry.data[CONF_TITLE])],
            config_subentry_id=subentry_id,
        )


class _HubSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True

    def __init__(self, hub: NotificationHub) -> None:
        self.hub = hub

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            self._set(state.state == STATE_ON)

    def _set(self, value: bool) -> None:
        raise NotImplementedError

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._set(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._set(False)
        self.async_write_ha_state()


class DoNotDisturbSwitch(_HubSwitch):
    """Nicht stören: nur kritische Benachrichtigungen kommen durch."""

    _attr_translation_key = "do_not_disturb"

    def __init__(self, hub: NotificationHub) -> None:
        super().__init__(hub)
        entry_id = hub.entry.entry_id
        self._attr_unique_id = f"{entry_id}_do_not_disturb"
        # Gerät wird in devices.py angelegt, hier nur verknüpfen
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry_id)})

    @property
    def is_on(self) -> bool:
        return self.hub.do_not_disturb

    def _set(self, value: bool) -> None:
        self.hub.do_not_disturb = value


class MuteSwitch(_HubSwitch):
    """Stumm: dieser Typ wird nicht gesendet (außer kritisch)."""

    _attr_translation_key = "mute"

    def __init__(
        self, hub: NotificationHub, subentry_id: str, key: str, title: str
    ) -> None:
        super().__init__(hub)
        self._key = key
        self._attr_unique_id = f"{subentry_id}_mute"
        # Gerät wird in devices.py angelegt, hier nur verknüpfen
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, subentry_id)})

    @property
    def is_on(self) -> bool:
        return self._key in self.hub.muted_types

    def _set(self, value: bool) -> None:
        if value:
            self.hub.muted_types.add(self._key)
        else:
            self.hub.muted_types.discard(self._key)
