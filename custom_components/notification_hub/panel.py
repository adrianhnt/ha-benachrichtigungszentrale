"""Eigene Seite „Benachrichtigungen“ in der Seitenleiste."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_URL_PATH,
)

FRONTEND_DIR = Path(__file__).parent / "frontend"
PANEL_FILE = "notification-hub-panel.js"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Skript bereitstellen und Seite registrieren (einmal beim Start)."""
    if hass.data.get(f"{DOMAIN}_panel"):
        return
    hass.data[f"{DOMAIN}_panel"] = True

    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_STATIC_URL, str(FRONTEND_DIR), False)]
    )

    # Version im Link, damit der Browser nach einem Update die neue Datei lädt
    stat = await hass.async_add_executor_job((FRONTEND_DIR / PANEL_FILE).stat)
    module_url = f"{PANEL_STATIC_URL}/{PANEL_FILE}?v={int(stat.st_mtime)}"

    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title=PANEL_TITLE,
        sidebar_icon=PANEL_ICON,
        module_url=module_url,
        require_admin=True,
        config={},
    )
