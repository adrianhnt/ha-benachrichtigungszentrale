"""Benachrichtigungszentrale: zentrale Verwaltung von Push-Benachrichtigungen."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_ACTIONS,
    ATTR_DATA,
    ATTR_DEVICES,
    ATTR_MESSAGE,
    ATTR_PERSONS,
    ATTR_PRIORITY,
    ATTR_TAG,
    ATTR_TITLE,
    ATTR_TYPE,
    ATTR_URL,
    DOMAIN,
    MOBILE_APP_ACTION_EVENT,
    PRIORITIES,
    PRIORITY_ACTIVE,
    SERVICE_CLEAR,
    SERVICE_SEND,
)
from .devices import async_setup_devices
from .hub import NotificationHub

type NotificationHubConfigEntry = ConfigEntry[NotificationHub]

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LIST = vol.All(cv.ensure_list, [cv.string])

SEND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TYPE): cv.string,
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_PRIORITY, default=PRIORITY_ACTIVE): vol.In(PRIORITIES),
        vol.Optional(ATTR_PERSONS): _LIST,
        vol.Optional(ATTR_DEVICES): _LIST,
        vol.Optional(ATTR_ACTIONS): _LIST,
        vol.Optional(ATTR_TAG): cv.string,
        vol.Optional(ATTR_URL): cv.string,
        vol.Optional(ATTR_DATA): dict,
    }
)

CLEAR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_TAG): cv.string,
        vol.Optional(ATTR_PERSONS): _LIST,
        vol.Optional(ATTR_DEVICES): _LIST,
    }
)


def _get_hub(hass: HomeAssistant) -> NotificationHub:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if isinstance(getattr(entry, "runtime_data", None), NotificationHub):
            return entry.runtime_data
    raise ServiceValidationError("Die Benachrichtigungszentrale ist nicht geladen.")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Dienste registrieren."""

    async def handle_send(call: ServiceCall) -> ServiceResponse:
        hub = _get_hub(hass)
        data: dict[str, Any] = call.data
        result = await hub.async_send(
            type_key=data[ATTR_TYPE],
            message=data[ATTR_MESSAGE],
            title=data.get(ATTR_TITLE),
            priority=data[ATTR_PRIORITY],
            persons=data.get(ATTR_PERSONS),
            devices=data.get(ATTR_DEVICES),
            action_keys=data.get(ATTR_ACTIONS),
            tag=data.get(ATTR_TAG),
            url=data.get(ATTR_URL),
            extra_data=data.get(ATTR_DATA),
        )
        return result if call.return_response else None

    async def handle_clear(call: ServiceCall) -> None:
        hub = _get_hub(hass)
        await hub.async_clear(
            call.data[ATTR_TAG],
            persons=call.data.get(ATTR_PERSONS),
            devices=call.data.get(ATTR_DEVICES),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND,
        handle_send,
        schema=SEND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR, handle_clear, schema=CLEAR_SCHEMA
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: NotificationHubConfigEntry
) -> bool:
    """Integration starten."""
    hub = NotificationHub(hass, entry)
    await hub.async_load()
    entry.runtime_data = hub

    # Geräte für Zentrale, Typen und Aktionen (Auswahllisten in Automationen)
    async_setup_devices(hass, entry)

    entry.async_on_unload(
        hass.bus.async_listen(MOBILE_APP_ACTION_EVENT, hub.async_handle_event)
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: NotificationHubConfigEntry
) -> None:
    """Bei Änderungen (Typen, Aktionen, Einstellungen) neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: NotificationHubConfigEntry
) -> bool:
    """Integration entladen."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_save_now()
    return unloaded
