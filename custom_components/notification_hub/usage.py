"""Wo werden Benachrichtigungen, Kategorien und Knöpfe verwendet?

Durchsucht die geladenen Automationen und Skripte nach Aufrufen von
notification_hub.send. Wird bei jedem Öffnen der Seite neu berechnet.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    ATTR_ACTIONS,
    ATTR_ID,
    ATTR_TYPE,
    DOMAIN,
    SERVICE_SEND,
    SUBENTRY_ACTION,
    SUBENTRY_TYPE,
)
from .hub import NotificationHub

SEND_ACTION = f"{DOMAIN}.{SERVICE_SEND}"


# Felder eines Aufrufs, die Vorgaben aus der Tabelle überschreiben
OVERRIDE_FIELDS = ("priority", "title", "message", "persons", "devices", "url", "tag", "data")


def _calls(node: Any) -> Iterator[dict[str, Any]]:
    """Alle aktiven Aufrufe von notification_hub.send in einer Konfiguration finden.

    Deaktivierte Schritte (enabled: false) und alles darunter werden übersprungen.
    """
    if isinstance(node, dict):
        if node.get("enabled") is False:
            return
        action = node.get("action") or node.get("service")
        if action == SEND_ACTION:
            data = node.get("data")
            yield data if isinstance(data, dict) else {}
        for value in node.values():
            yield from _calls(value)
    elif isinstance(node, list):
        for item in node:
            yield from _calls(item)


def _is_template(value: Any) -> bool:
    return isinstance(value, str) and ("{{" in value or "{%" in value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _sources(hass: HomeAssistant) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    """(Verweis, Konfiguration) aller Automationen und Skripte."""
    for domain in ("automation", "script"):
        component = hass.data.get(domain)
        entities = getattr(component, "entities", None)
        if entities is None:
            continue
        for entity in entities:
            raw = getattr(entity, "raw_config", None)
            if not isinstance(raw, dict):
                continue
            state = hass.states.get(entity.entity_id)
            if domain == "automation":
                config_id = raw.get("id")
                url = f"/config/automation/edit/{config_id}" if config_id else None
                enabled = state is not None and state.state == "on"
            else:
                key = entity.entity_id.split(".", 1)[1]
                url = f"/config/script/edit/{key}"
                enabled = True
            name = (
                state.attributes.get("friendly_name")
                if state is not None
                else None
            ) or raw.get("alias") or entity.entity_id
            yield (
                {
                    "entity_id": entity.entity_id,
                    "name": name,
                    "kind": domain,
                    "url": url,
                    "enabled": enabled,
                },
                raw,
            )


def _overrides(data: dict[str, Any]) -> dict[str, Any]:
    """Was dieser Aufruf gegenüber der Tabelle überschreibt (für die Anzeige)."""
    out: dict[str, Any] = {}
    for key in OVERRIDE_FIELDS:
        value = data.get(key)
        if value in (None, "", [], {}):
            continue
        if _is_template(value):
            out[key] = {"template": True}
        elif isinstance(value, (list, dict)):
            out[key] = value
        else:
            out[key] = str(value)
    return out


def collect_usage(hass: HomeAssistant, hub: NotificationHub) -> dict[str, Any]:
    """Verwendung pro Benachrichtigung, Kategorie und Knopf ermitteln."""
    usage: dict[str, Any] = {
        "notifications": {},
        "categories": {},
        "buttons": {},
        "dynamic": [],
    }

    def add(bucket: str, key: str, ref: dict[str, Any]) -> None:
        refs = usage[bucket].setdefault(key, [])
        if all(r["entity_id"] != ref["entity_id"] for r in refs):
            refs.append(ref)

    for ref, raw in _sources(hass):
        for data in _calls(raw):
            nid = data.get(ATTR_ID)
            if _is_template(nid):
                if all(r["entity_id"] != ref["entity_id"] for r in usage["dynamic"]):
                    usage["dynamic"].append(ref)
            elif isinstance(nid, str) and nid:
                refs = usage["notifications"].setdefault(nid, [])
                entry = next((r for r in refs if r["entity_id"] == ref["entity_id"]), None)
                if entry is None:
                    entry = {**ref, "calls": []}
                    refs.append(entry)
                entry["calls"].append({"overrides": _overrides(data)})
                continue

            # Bisherige Variante: Typ und Knöpfe direkt im Aufruf
            type_value = data.get(ATTR_TYPE)
            if isinstance(type_value, str) and not _is_template(type_value):
                add("categories", hub.resolve_key(type_value, SUBENTRY_TYPE), ref)
            for action in _as_list(data.get(ATTR_ACTIONS)):
                if isinstance(action, str) and not _is_template(action):
                    add("buttons", hub.resolve_key(action, SUBENTRY_ACTION), ref)

    return usage
