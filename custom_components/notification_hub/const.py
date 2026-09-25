"""Konstanten der Benachrichtigungszentrale."""

from __future__ import annotations

DOMAIN = "notification_hub"
NAME = "Benachrichtigungszentrale"

# Subentry-Arten
SUBENTRY_TYPE = "notification_type"
SUBENTRY_ACTION = "notification_action"

# Felder Benachrichtigungstyp
CONF_KEY = "key"
CONF_TITLE = "title"
CONF_GROUP = "group"

# Felder Aktion
CONF_BUTTON_TITLE = "button_title"
CONF_ICON = "icon"
CONF_SERVICE = "service"
CONF_TARGET_ENTITIES = "target_entities"
CONF_SERVICE_DATA = "service_data"
CONF_STEPS = "steps"  # Liste von {service, target_entities, service_data}
MAX_STEPS = 20


def button_steps(data) -> list[dict]:
    """Schritte eines Knopfs – auch für Knöpfe aus Versionen ohne Schritt-Liste."""
    steps = data.get(CONF_STEPS)
    if steps:
        return [dict(step) for step in steps]
    if data.get(CONF_SERVICE):
        return [
            {
                CONF_SERVICE: data[CONF_SERVICE],
                CONF_TARGET_ENTITIES: list(data.get(CONF_TARGET_ENTITIES) or []),
                CONF_SERVICE_DATA: dict(data.get(CONF_SERVICE_DATA) or {}),
            }
        ]
    return []
CONF_EXPIRY_MINUTES = "expiry_minutes"
CONF_AUTH_REQUIRED = "authentication_required"
CONF_DESTRUCTIVE = "destructive"

# Globale Optionen
CONF_CRITICAL_VOLUME = "critical_volume"
CONF_CRITICAL_SOUND = "critical_sound"
CONF_TIME_SENSITIVE_SOUND = "time_sensitive_sound"
CONF_EXPIRED_FEEDBACK = "expired_feedback"

DEFAULT_OPTIONS = {
    CONF_CRITICAL_VOLUME: 100,
    CONF_CRITICAL_SOUND: "default",
    CONF_TIME_SENSITIVE_SOUND: "default",
    CONF_EXPIRED_FEEDBACK: True,
}

# Dringlichkeiten (Werte = iOS interruption-level)
PRIORITY_PASSIVE = "passive"
PRIORITY_ACTIVE = "active"
PRIORITY_TIME_SENSITIVE = "time-sensitive"
PRIORITY_CRITICAL = "critical"
PRIORITIES = [
    PRIORITY_PASSIVE,
    PRIORITY_ACTIVE,
    PRIORITY_TIME_SENSITIVE,
    PRIORITY_CRITICAL,
]

# Dienste und Felder
SERVICE_SEND = "send"
SERVICE_CLEAR = "clear"
ATTR_TYPE = "type"
ATTR_MESSAGE = "message"
ATTR_TITLE = "title"
ATTR_PRIORITY = "priority"
ATTR_PERSONS = "persons"
ATTR_DEVICES = "devices"
ATTR_ACTIONS = "actions"
ATTR_TAG = "tag"
ATTR_URL = "url"
ATTR_DATA = "data"
ATTR_ID = "id"
ATTR_VARIABLES = "variables"

# Gerätemodelle (für die Auswahl in Automationen)
MODEL_HUB = "Zentrale"
MODEL_TYPE = "Benachrichtigungstyp"
MODEL_ACTION = "Aktion"

# Gültigkeit einer Aktion: höchstens 30 Tage (= Aufbewahrung des Verlaufs)
MAX_EXPIRY_MINUTES = 30 * 24 * 60

# Zentral verwaltete Benachrichtigungen (eigener Speicher, nicht als Subentry)
NOTIFICATIONS_STORAGE_KEY = f"{DOMAIN}.notifications"
NOTIFICATIONS_STORAGE_VERSION = 1
N_ID = "id"
N_CATEGORY = "category"
N_TITLE = "title"
N_MESSAGE = "message"
N_PRIORITY = "priority"
N_PERSONS = "persons"
N_DEVICES = "devices"
N_ACTIONS = "actions"
N_URL = "url"
N_NOTE = "note"

# Seite in der Seitenleiste
PANEL_URL_PATH = "benachrichtigungen"
PANEL_TITLE = "Benachrichtigungen"
PANEL_ICON = "mdi:bell-cog-outline"
PANEL_ELEMENT = "notification-hub-panel"
PANEL_STATIC_URL = f"/{DOMAIN}_static"

# Kennung in der Knopf-ID
ACTION_PREFIX = "NHUB"

# Ereignis, das bei jedem Knopfdruck gefeuert wird
EVENT_ACTION = f"{DOMAIN}_action"

# Mobile-App-Ereignis bei Knopfdruck
MOBILE_APP_ACTION_EVENT = "mobile_app_notification_action"

# Speicher
STORAGE_KEY = f"{DOMAIN}.history"
STORAGE_VERSION = 1
HISTORY_MAX_AGE_DAYS = 30
HISTORY_MAX_ENTRIES = 500

SIGNAL_SENT = f"{DOMAIN}_sent"
