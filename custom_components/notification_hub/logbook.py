"""Knopfdrücke im Logbuch anzeigen."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback

from .const import DOMAIN, EVENT_ACTION, NAME

RESULT_TEXT = {
    "executed": "ausgeführt",
    "expired": "abgelaufen, nicht ausgeführt",
    "failed": "fehlgeschlagen",
    "already_handled": "bereits erledigt, nicht erneut ausgeführt",
    "unknown": "Benachrichtigung unbekannt, nicht ausgeführt",
    "unknown_action": "Aktion gibt es nicht mehr, nicht ausgeführt",
}


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[
        [str, str, Callable[[Event], dict[str, Any]]], None
    ],
) -> None:
    """Beschreibung für das Knopf-Ereignis registrieren."""

    @callback
    def describe(event: Event) -> dict[str, Any]:
        data = event.data
        title = data.get("action_title") or data.get("action") or "?"
        result = RESULT_TEXT.get(data.get("result"), data.get("result") or "?")
        device = data.get("device_name")
        where = f" auf {device}" if device else ""
        return {
            LOGBOOK_ENTRY_NAME: NAME,
            LOGBOOK_ENTRY_MESSAGE: f"Knopf „{title}“ gedrückt{where}: {result}",
        }

    async_describe_event(DOMAIN, EVENT_ACTION, describe)
