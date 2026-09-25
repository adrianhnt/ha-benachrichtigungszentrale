"""Einrichtung und Verwaltung der Benachrichtigungszentrale."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    ObjectSelector,
    TextSelector,
)
from homeassistant.util import slugify

from .const import (
    CONF_AUTH_REQUIRED,
    CONF_BUTTON_TITLE,
    CONF_CRITICAL_SOUND,
    CONF_CRITICAL_VOLUME,
    CONF_DESTRUCTIVE,
    CONF_EXPIRED_FEEDBACK,
    CONF_EXPIRY_MINUTES,
    CONF_GROUP,
    CONF_ICON,
    CONF_KEY,
    CONF_SERVICE,
    CONF_SERVICE_DATA,
    CONF_TARGET_ENTITIES,
    CONF_TIME_SENSITIVE_SOUND,
    CONF_TITLE,
    DEFAULT_OPTIONS,
    DOMAIN,
    MAX_EXPIRY_MINUTES,
    NAME,
    SUBENTRY_ACTION,
    SUBENTRY_TYPE,
)

SERVICE_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def _options_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CRITICAL_VOLUME): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=100, step=5, unit_of_measurement="%",
                    mode=NumberSelectorMode.SLIDER,
                )
            ),
            vol.Required(CONF_CRITICAL_SOUND): TextSelector(),
            vol.Required(CONF_TIME_SENSITIVE_SOUND): TextSelector(),
            vol.Required(CONF_EXPIRED_FEEDBACK): BooleanSelector(),
        }
    )


class NotificationHubConfigFlow(ConfigFlow, domain=DOMAIN):
    """Einrichtung der Benachrichtigungszentrale."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Einrichtung bestätigen."""
        if user_input is not None:
            return self.async_create_entry(
                title=NAME, data={}, options=dict(DEFAULT_OPTIONS)
            )
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Globale Einstellungen."""
        return NotificationHubOptionsFlow()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Benachrichtigungstypen und Aktionen als Unter-Einträge."""
        return {
            SUBENTRY_TYPE: NotificationTypeSubentryFlow,
            SUBENTRY_ACTION: NotificationActionSubentryFlow,
        }


class NotificationHubOptionsFlow(OptionsFlow):
    """Globale Einstellungen (Lautstärke, Töne)."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Einstellungen anzeigen und speichern."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**DEFAULT_OPTIONS, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _options_schema(), current
            ),
        )


def _key_error(
    entry: ConfigEntry, subentry_type: str, key: str, own_subentry_id: str | None
) -> str | None:
    if not key or slugify(key) != key:
        return "invalid_key"
    for sub in entry.subentries.values():
        if (
            sub.subentry_type == subentry_type
            and sub.data.get(CONF_KEY) == key
            and sub.subentry_id != own_subentry_id
        ):
            return "duplicate_key"
    return None


class NotificationTypeSubentryFlow(ConfigSubentryFlow):
    """Benachrichtigungstyp anlegen / bearbeiten."""

    def _schema(self, with_key: bool) -> vol.Schema:
        fields: dict[Any, Any] = {}
        if with_key:
            fields[vol.Required(CONF_KEY)] = TextSelector()
        fields[vol.Required(CONF_TITLE)] = TextSelector()
        fields[vol.Optional(CONF_GROUP)] = TextSelector()
        return vol.Schema(fields)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Neuen Typ anlegen."""
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_KEY].strip()
            if err := _key_error(self._get_entry(), SUBENTRY_TYPE, key, None):
                errors[CONF_KEY] = err
            else:
                data = {**user_input, CONF_KEY: key}
                return self.async_create_entry(
                    title=f"{data[CONF_TITLE]} ({key})", data=data, unique_id=key
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(True), user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Typ bearbeiten (Kennung bleibt fest)."""
        subentry = self._get_reconfigure_subentry()
        key = subentry.data[CONF_KEY]
        if user_input is not None:
            data = {**user_input, CONF_KEY: key}
            return self.async_update_and_abort(
                self._get_entry(),
                subentry,
                title=f"{data[CONF_TITLE]} ({key})",
                data=data,
            )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(False), dict(subentry.data)
            ),
            description_placeholders={"key": key},
        )


class NotificationActionSubentryFlow(ConfigSubentryFlow):
    """Aktion (Knopf) anlegen / bearbeiten."""

    def _schema(self, with_key: bool) -> vol.Schema:
        fields: dict[Any, Any] = {}
        if with_key:
            fields[vol.Required(CONF_KEY)] = TextSelector()
        fields.update(
            {
                vol.Required(CONF_BUTTON_TITLE): TextSelector(),
                vol.Optional(CONF_ICON): TextSelector(),
                vol.Required(CONF_SERVICE): TextSelector(),
                vol.Optional(CONF_TARGET_ENTITIES): EntitySelector(
                    EntitySelectorConfig(multiple=True)
                ),
                vol.Optional(CONF_SERVICE_DATA): ObjectSelector(),
                vol.Optional(CONF_EXPIRY_MINUTES, default=0): NumberSelector(
                    NumberSelectorConfig(
                        min=0, max=MAX_EXPIRY_MINUTES, step=1, unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(CONF_AUTH_REQUIRED, default=False): BooleanSelector(),
                vol.Optional(CONF_DESTRUCTIVE, default=False): BooleanSelector(),
            }
        )
        return vol.Schema(fields)

    def _validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        service = user_input[CONF_SERVICE].strip()
        if not SERVICE_RE.match(service):
            errors[CONF_SERVICE] = "invalid_service"
        elif not self.hass.services.has_service(*service.split(".", 1)):
            errors[CONF_SERVICE] = "unknown_service"
        service_data = user_input.get(CONF_SERVICE_DATA)
        if service_data not in (None, "") and not isinstance(service_data, dict):
            errors[CONF_SERVICE_DATA] = "invalid_service_data"
        return errors

    @staticmethod
    def _clean(user_input: dict[str, Any], key: str) -> dict[str, Any]:
        data = {**user_input, CONF_KEY: key}
        data[CONF_SERVICE] = data[CONF_SERVICE].strip()
        data[CONF_EXPIRY_MINUTES] = int(data.get(CONF_EXPIRY_MINUTES) or 0)
        if not data.get(CONF_SERVICE_DATA):
            data.pop(CONF_SERVICE_DATA, None)
        if data.get(CONF_ICON):
            data[CONF_ICON] = data[CONF_ICON].strip().removeprefix("sfsymbols:")
        return data

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Neue Aktion anlegen."""
        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input[CONF_KEY].strip()
            if err := _key_error(self._get_entry(), SUBENTRY_ACTION, key, None):
                errors[CONF_KEY] = err
            errors.update(self._validate(user_input))
            if not errors:
                data = self._clean(user_input, key)
                return self.async_create_entry(
                    title=f"{data[CONF_BUTTON_TITLE]} ({key})",
                    data=data,
                    unique_id=key,
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(True), user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Aktion bearbeiten (Kennung bleibt fest)."""
        subentry = self._get_reconfigure_subentry()
        key = subentry.data[CONF_KEY]
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = self._validate(user_input)
            if not errors:
                data = self._clean(user_input, key)
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=f"{data[CONF_BUTTON_TITLE]} ({key})",
                    data=data,
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                self._schema(False), user_input or dict(subentry.data)
            ),
            errors=errors,
            description_placeholders={"key": key},
        )
