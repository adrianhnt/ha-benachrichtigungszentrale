"""Geräte der Benachrichtigungszentrale.

Die Zentrale selbst, jeder Benachrichtigungstyp und jede Aktion ist ein eigenes
Gerät. So kann man Typen und Aktionen in Automationen aus einer Liste auswählen
(Geräteauswahl, gefiltert nach Modell), statt die Kennung einzutippen.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_BUTTON_TITLE,
    CONF_TITLE,
    DOMAIN,
    MODEL_ACTION,
    MODEL_HUB,
    MODEL_TYPE,
    NAME,
    SUBENTRY_ACTION,
    SUBENTRY_TYPE,
)


def type_device_name(title: str) -> str:
    """Name des Geräts für einen Benachrichtigungstyp."""
    return f"Benachrichtigung {title}"


def action_device_name(button_title: str) -> str:
    """Name des Geräts für eine Aktion."""
    return f"Aktion {button_title}"


@callback
def async_setup_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Geräte für Zentrale, Typen und Aktionen anlegen bzw. aktualisieren.

    Die Kennungen der Geräte ((DOMAIN, subentry_id)) sind dieselben wie in
    Version 0.1.0, bestehende Geräte behalten also ihre ID.
    """
    dev_reg = dr.async_get(hass)

    hub_device = dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=NAME,
        model=MODEL_HUB,
        entry_type=dr.DeviceEntryType.SERVICE,
    )

    wanted: set[str] = {entry.entry_id}
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type == SUBENTRY_TYPE:
            name = type_device_name(subentry.data[CONF_TITLE])
            model = MODEL_TYPE
        elif subentry.subentry_type == SUBENTRY_ACTION:
            name = action_device_name(subentry.data[CONF_BUTTON_TITLE])
            model = MODEL_ACTION
        else:
            continue
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=subentry_id,
            identifiers={(DOMAIN, subentry_id)},
            name=name,
            model=model,
            entry_type=dr.DeviceEntryType.SERVICE,
            via_device_id=hub_device.id,
        )
        wanted.add(subentry_id)

    # Geräte von gelöschten Typen/Aktionen aufräumen
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        ids = {ident for dom, ident in device.identifiers if dom == DOMAIN}
        if ids and not ids & wanted:
            dev_reg.async_remove_device(device.id)
