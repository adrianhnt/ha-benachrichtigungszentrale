"""Benachrichtigungszentrale: zentrale Verwaltung von Push-Benachrichtigungen."""

from __future__ import annotations

from pathlib import Path
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
from homeassistant.util.yaml import load_yaml_dict

from .const import (
    ATTR_ACTIONS,
    ATTR_DATA,
    ATTR_DEVICES,
    ATTR_ID,
    ATTR_MESSAGE,
    ATTR_PERSONS,
    ATTR_PRIORITY,
    ATTR_TAG,
    ATTR_TITLE,
    ATTR_TYPE,
    ATTR_URL,
    ATTR_VARIABLES,
    DOMAIN,
    MOBILE_APP_ACTION_EVENT,
    PRIORITIES,
    PRIORITY_ACTIVE,
    SERVICE_CLEAR,
    SERVICE_SEND,
)
from .devices import async_setup_devices
from .hub import NotificationHub
from .panel import async_register_panel
from .websocket import async_register_websocket_commands

type NotificationHubConfigEntry = ConfigEntry[NotificationHub]

PLATFORMS: list[Platform] = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LIST = vol.All(cv.ensure_list, [cv.string])

SEND_SCHEMA = vol.Schema(
    {
        # Entweder eine zentral verwaltete Benachrichtigung (id) ...
        vol.Optional(ATTR_ID): cv.string,
        vol.Optional(ATTR_VARIABLES): dict,
        # ... oder alles direkt im Aufruf (bisherige Variante)
        vol.Optional(ATTR_TYPE): cv.string,
        vol.Optional(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_PRIORITY): vol.In(PRIORITIES),
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
        if data.get(ATTR_ID):
            result = await hub.async_send_notification(
                data[ATTR_ID],
                persons=data.get(ATTR_PERSONS),
                devices=data.get(ATTR_DEVICES),
                variables=data.get(ATTR_VARIABLES),
                title=data.get(ATTR_TITLE),
                message=data.get(ATTR_MESSAGE),
                priority=data.get(ATTR_PRIORITY),
                tag=data.get(ATTR_TAG),
                url=data.get(ATTR_URL),
                extra_data=data.get(ATTR_DATA),
            )
            return result if call.return_response else None
        if not data.get(ATTR_TYPE) or not data.get(ATTR_MESSAGE):
            raise ServiceValidationError(
                "Bitte eine Benachrichtigung (id) angeben – oder Typ und Nachricht."
            )
        result = await hub.async_send(
            type_key=data[ATTR_TYPE],
            message=data[ATTR_MESSAGE],
            title=data.get(ATTR_TITLE),
            priority=data.get(ATTR_PRIORITY) or PRIORITY_ACTIVE,
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

    # Grundlage für die dynamische Auswahlliste der IDs
    hass.data[f"{DOMAIN}_services_yaml"] = await hass.async_add_executor_job(
        load_yaml_dict, str(Path(__file__).parent / "services.yaml")
    )

    async_register_websocket_commands(hass)
    await async_register_panel(hass)
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
    hub.publish_service_schema()

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
