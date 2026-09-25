"""Schnittstelle für die Seite „Benachrichtigungen“ (nur für Administratoren)."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .config_flow import SERVICE_RE, _key_error
from .const import (
    CONF_AUTH_REQUIRED,
    CONF_BUTTON_TITLE,
    CONF_DESTRUCTIVE,
    CONF_EXPIRY_MINUTES,
    CONF_GROUP,
    CONF_ICON,
    CONF_KEY,
    CONF_SERVICE,
    CONF_SERVICE_DATA,
    CONF_TARGET_ENTITIES,
    CONF_TITLE,
    DOMAIN,
    MAX_EXPIRY_MINUTES,
    N_ACTIONS,
    N_CATEGORY,
    PRIORITIES,
    SUBENTRY_ACTION,
    SUBENTRY_TYPE,
)
from .hub import NotificationHub
from .usage import collect_usage


def _hub(hass: HomeAssistant) -> NotificationHub:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if isinstance(getattr(entry, "runtime_data", None), NotificationHub):
            return entry.runtime_data
    raise HomeAssistantError("Die Benachrichtigungszentrale ist gerade nicht geladen.")


@callback
def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Befehle registrieren (einmal beim Start)."""
    for command in (
        ws_data,
        ws_notification_save,
        ws_notification_delete,
        ws_notification_test,
        ws_category_save,
        ws_button_save,
        ws_subentry_delete,
    ):
        websocket_api.async_register_command(hass, command)


# ----------------------------------------------------------------------
# Lesen
# ----------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/data"})
@callback
def ws_data(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Alles, was die Seite anzeigt."""
    try:
        hub = _hub(hass)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_loaded", str(err))
        return
    entry = hub.entry
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)

    device_by_sub: dict[str, str] = {}
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        for dom, ident in device.identifiers:
            if dom == DOMAIN:
                device_by_sub[ident] = device.id

    categories = []
    buttons = []
    for sub_id, sub in entry.subentries.items():
        data = dict(sub.data)
        if sub.subentry_type == SUBENTRY_TYPE:
            mute_entity = ent_reg.async_get_entity_id("switch", DOMAIN, f"{sub_id}_mute")
            state = hass.states.get(mute_entity) if mute_entity else None
            categories.append(
                {
                    "subentry_id": sub_id,
                    "device_id": device_by_sub.get(sub_id),
                    "key": data.get(CONF_KEY),
                    "title": data.get(CONF_TITLE, ""),
                    "group": data.get(CONF_GROUP, ""),
                    "mute_entity_id": mute_entity,
                    "muted": state is not None and state.state == "on",
                }
            )
        elif sub.subentry_type == SUBENTRY_ACTION:
            buttons.append(
                {
                    "subentry_id": sub_id,
                    "device_id": device_by_sub.get(sub_id),
                    "key": data.get(CONF_KEY),
                    "button_title": data.get(CONF_BUTTON_TITLE, ""),
                    "icon": data.get(CONF_ICON, ""),
                    "service": data.get(CONF_SERVICE, ""),
                    "target_entities": list(data.get(CONF_TARGET_ENTITIES) or []),
                    "service_data": data.get(CONF_SERVICE_DATA) or {},
                    "expiry_minutes": data.get(CONF_EXPIRY_MINUTES) or 0,
                    "authentication_required": bool(data.get(CONF_AUTH_REQUIRED)),
                    "destructive": bool(data.get(CONF_DESTRUCTIVE)),
                }
            )

    targets = [
        {
            "device_id": t.device_id,
            "name": t.name,
            "critical_volume": hub.critical_volume(t.device_id),
            "volume_entity_id": ent_reg.async_get_entity_id(
                "number", DOMAIN, f"{entry.entry_id}_{t.app_device_id}_critical_volume"
            ),
        }
        for t in hub.async_get_targets().values()
    ]
    persons = [
        {"entity_id": s.entity_id, "name": s.name}
        for s in hass.states.async_all("person")
    ]

    connection.send_result(
        msg["id"],
        {
            "categories": sorted(categories, key=lambda c: c["title"].lower()),
            "buttons": sorted(buttons, key=lambda b: b["button_title"].lower()),
            "notifications": sorted(hub.notifications.values(), key=lambda n: n["id"]),
            "targets": sorted(targets, key=lambda t: t["name"].lower()),
            "persons": sorted(persons, key=lambda p: p["name"].lower()),
            "priorities": PRIORITIES,
            "usage": collect_usage(hass, hub),
            "do_not_disturb": hub.do_not_disturb,
            "max_expiry_minutes": MAX_EXPIRY_MINUTES,
        },
    )


# ----------------------------------------------------------------------
# Benachrichtigungen
# ----------------------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/notification/save",
        vol.Required("notification"): dict,
        vol.Optional("original_id"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_notification_save(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Benachrichtigung anlegen oder ändern."""
    try:
        saved = await _hub(hass).async_save_notification(
            msg["notification"], msg.get("original_id")
        )
    except (ValueError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"], saved)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/notification/delete", vol.Required("notification_id"): str}
)
@websocket_api.async_response
async def ws_notification_delete(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Benachrichtigung löschen."""
    try:
        await _hub(hass).async_delete_notification(msg["notification_id"])
    except (ValueError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/notification/test", vol.Required("notification_id"): str}
)
@websocket_api.async_response
async def ws_notification_test(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Test an die Standard-Empfänger senden – genau wie aus einer Automation, nur mit 🧪 im Titel."""
    try:
        result = await _hub(hass).async_send_notification(msg["notification_id"], test=True)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "failed", str(err))
        return
    connection.send_result(msg["id"], result)


# ----------------------------------------------------------------------
# Kategorien und Knöpfe (bleiben Unter-Einträge der Integration)
# ----------------------------------------------------------------------


def _save_subentry(hass: HomeAssistant, hub: NotificationHub, subentry_type: str, subentry_id: str | None, data: dict[str, Any], title: str) -> None:
    entry = hub.entry
    key = data[CONF_KEY]
    if subentry_id is None:
        if err := _key_error(entry, subentry_type, key, None):
            raise ValueError(
                "Diese Kennung gibt es schon."
                if err == "duplicate_key"
                else "Die Kennung darf nur Kleinbuchstaben, Zahlen und _ enthalten."
            )
        hass.config_entries.async_add_subentry(
            entry,
            ConfigSubentry(
                data=MappingProxyType(data),
                subentry_type=subentry_type,
                title=title,
                unique_id=key,
            ),
        )
        return
    subentry = entry.subentries.get(subentry_id)
    if subentry is None or subentry.subentry_type != subentry_type:
        raise ValueError("Diesen Eintrag gibt es nicht mehr.")
    data[CONF_KEY] = subentry.data[CONF_KEY]  # Kennung bleibt fest
    hass.config_entries.async_update_subentry(entry, subentry, data=data, title=title)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/category/save",
        vol.Optional("subentry_id"): vol.Any(str, None),
        vol.Required("key"): str,
        vol.Required("title"): str,
        vol.Optional("group"): str,
    }
)
@callback
def ws_category_save(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Kategorie (Benachrichtigungstyp) anlegen oder ändern."""
    try:
        hub = _hub(hass)
        key = msg["key"].strip()
        title = msg["title"].strip()
        if not title:
            raise ValueError("Der Name darf nicht leer sein.")
        data: dict[str, Any] = {CONF_KEY: key, CONF_TITLE: title}
        if msg.get("group", "").strip():
            data[CONF_GROUP] = msg["group"].strip()
        _save_subentry(hass, hub, SUBENTRY_TYPE, msg.get("subentry_id"), data, f"{title} ({key})")
    except (ValueError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/button/save",
        vol.Optional("subentry_id"): vol.Any(str, None),
        vol.Required("key"): str,
        vol.Required("button_title"): str,
        vol.Optional("icon"): str,
        vol.Required("service"): str,
        vol.Optional("target_entities"): [str],
        vol.Optional("service_data"): dict,
        vol.Optional("expiry_minutes"): vol.Coerce(int),
        vol.Optional("authentication_required"): bool,
        vol.Optional("destructive"): bool,
    }
)
@callback
def ws_button_save(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Knopf (Aktion) anlegen oder ändern."""
    try:
        hub = _hub(hass)
        key = msg["key"].strip()
        button_title = msg["button_title"].strip()
        service = msg["service"].strip()
        if not button_title:
            raise ValueError("Der Knopftext darf nicht leer sein.")
        if not SERVICE_RE.match(service):
            raise ValueError("Dienst im Format domain.dienst angeben, z. B. switch.turn_on.")
        if not hass.services.has_service(*service.split(".", 1)):
            raise ValueError(f"Den Dienst {service} gibt es nicht.")
        expiry = int(msg.get("expiry_minutes") or 0)
        if not 0 <= expiry <= MAX_EXPIRY_MINUTES:
            raise ValueError(f"Gültigkeit: 0 bis {MAX_EXPIRY_MINUTES} Minuten.")
        data: dict[str, Any] = {
            CONF_KEY: key,
            CONF_BUTTON_TITLE: button_title,
            CONF_SERVICE: service,
            CONF_TARGET_ENTITIES: list(msg.get("target_entities") or []),
            CONF_EXPIRY_MINUTES: expiry,
            CONF_AUTH_REQUIRED: bool(msg.get("authentication_required")),
            CONF_DESTRUCTIVE: bool(msg.get("destructive")),
        }
        icon = (msg.get("icon") or "").strip().removeprefix("sfsymbols:")
        if icon:
            data[CONF_ICON] = icon
        if msg.get("service_data"):
            data[CONF_SERVICE_DATA] = msg["service_data"]
        _save_subentry(hass, hub, SUBENTRY_ACTION, msg.get("subentry_id"), data, f"{button_title} ({key})")
    except (ValueError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/subentry/delete", vol.Required("subentry_id"): str}
)
@callback
def ws_subentry_delete(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Kategorie oder Knopf löschen – nur wenn keine Benachrichtigung sie nutzt."""
    try:
        hub = _hub(hass)
        subentry = hub.entry.subentries.get(msg["subentry_id"])
        if subentry is None:
            raise ValueError("Diesen Eintrag gibt es nicht mehr.")
        key = subentry.data.get(CONF_KEY)
        if subentry.subentry_type == SUBENTRY_TYPE:
            users = [n["id"] for n in hub.notifications.values() if n[N_CATEGORY] == key]
        else:
            users = [n["id"] for n in hub.notifications.values() if key in n[N_ACTIONS]]
        if users:
            raise ValueError(f"Wird noch verwendet von: {', '.join(sorted(users))}")
        hass.config_entries.async_remove_subentry(hub.entry, subentry.subentry_id)
    except (ValueError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    connection.send_result(msg["id"])
