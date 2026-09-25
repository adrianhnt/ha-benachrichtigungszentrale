"""Kernlogik der Benachrichtigungszentrale: Versand, Empfänger, Knopfdrücke."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any
import uuid

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.helpers.storage import Store
from homeassistant.helpers.template import Template
from homeassistant.exceptions import TemplateError
from homeassistant.util import dt as dt_util, slugify
from jinja2 import Environment, meta

from .const import (
    ACTION_PREFIX,
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
    EVENT_ACTION,
    HISTORY_MAX_AGE_DAYS,
    HISTORY_MAX_ENTRIES,
    N_ACTIONS,
    N_CATEGORY,
    N_DEVICES,
    N_ID,
    N_MESSAGE,
    N_NOTE,
    N_PERSONS,
    N_PRIORITY,
    N_TITLE,
    N_URL,
    NOTIFICATIONS_STORAGE_KEY,
    NOTIFICATIONS_STORAGE_VERSION,
    PRIORITIES,
    PRIORITY_ACTIVE,
    PRIORITY_CRITICAL,
    PRIORITY_PASSIVE,
    PRIORITY_TIME_SENSITIVE,
    SERVICE_SEND,
    SIGNAL_SENT,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUBENTRY_ACTION,
    SUBENTRY_TYPE,
)

_LOGGER = logging.getLogger(__name__)

MOBILE_APP_DOMAIN = "mobile_app"


@dataclass(frozen=True)
class Target:
    """Ein Gerät, das Benachrichtigungen empfangen kann."""

    device_id: str  # ID im HA-Geräteregister
    app_device_id: str  # ID, die die App selbst verwendet (sourceDeviceID)
    name: str
    notify_service: str  # z. B. mobile_app_adrians_iphone


class NotificationHub:
    """Hält Katalog, Zustand und Verlauf der Benachrichtigungen."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialisieren."""
        self.hass = hass
        self.entry = entry
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._history: dict[str, dict[str, Any]] = {}
        self._n_store: Store[dict[str, Any]] = Store(
            hass, NOTIFICATIONS_STORAGE_VERSION, NOTIFICATIONS_STORAGE_KEY
        )
        self.notifications: dict[str, dict[str, Any]] = {}
        self.do_not_disturb = False
        self.muted_types: set[str] = set()
        self.last_sent: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Katalog (aus den Subentries)
    # ------------------------------------------------------------------

    @property
    def options(self) -> dict[str, Any]:
        """Globale Einstellungen mit Standardwerten."""
        return {**DEFAULT_OPTIONS, **self.entry.options}

    def _catalog(self, subentry_type: str) -> dict[str, dict[str, Any]]:
        return {
            sub.data[CONF_KEY]: dict(sub.data)
            for sub in self.entry.subentries.values()
            if sub.subentry_type == subentry_type and CONF_KEY in sub.data
        }

    @callback
    def resolve_key(self, value: str, subentry_type: str) -> str:
        """Kennung oder Geräte-ID (aus der Auswahlliste) in die Kennung umwandeln.

        Unbekannte Werte werden unverändert zurückgegeben; die Prüfung, ob es
        den Typ bzw. die Aktion gibt, passiert beim Versand.
        """
        if value in self._catalog(subentry_type):
            return value
        device = dr.async_get(self.hass).async_get(value)
        if device is None:
            return value
        for domain, ident in device.identifiers:
            if domain != DOMAIN:
                continue
            subentry = self.entry.subentries.get(ident)
            if subentry and subentry.subentry_type == subentry_type:
                return subentry.data[CONF_KEY]
        return value

    @property
    def types(self) -> dict[str, dict[str, Any]]:
        """Alle Benachrichtigungstypen, nach Kennung."""
        return self._catalog(SUBENTRY_TYPE)

    @property
    def actions(self) -> dict[str, dict[str, Any]]:
        """Alle Aktionen, nach Kennung."""
        return self._catalog(SUBENTRY_ACTION)

    # ------------------------------------------------------------------
    # Speicher
    # ------------------------------------------------------------------

    async def async_load(self) -> None:
        """Verlauf und Benachrichtigungen laden."""
        n_data = await self._n_store.async_load() or {}
        self.notifications = {
            n[N_ID]: n for n in n_data.get("notifications", []) if N_ID in n
        }
        data = await self._store.async_load() or {}
        self._history = data.get("notifications", {})
        self._prune()
        if self._history:
            nid, rec = max(self._history.items(), key=lambda item: item[1]["sent_at"])
            self.last_sent = {
                "notification_id": nid,
                "sent_at": dt_util.parse_datetime(rec["sent_at"]),
                "id": rec.get("id"),
                "type": rec["type"],
                "title": rec["title"],
                "message": rec["message"],
                "priority": rec["priority"],
                "recipients": rec.get("recipients", []),
                "actions": list(rec["actions"]),
            }

    async def async_save_now(self) -> None:
        """Verlauf sofort speichern (beim Entladen)."""
        await self._store.async_save({"notifications": self._history})

    @callback
    def _schedule_save(self) -> None:
        self._store.async_delay_save(lambda: {"notifications": self._history}, 2)

    @callback
    def _prune(self) -> None:
        cutoff = dt_util.utcnow() - timedelta(days=HISTORY_MAX_AGE_DAYS)
        items = [
            (nid, rec)
            for nid, rec in self._history.items()
            if dt_util.parse_datetime(rec["sent_at"]) > cutoff
        ]
        items.sort(key=lambda item: item[1]["sent_at"])
        self._history = dict(items[-HISTORY_MAX_ENTRIES:])

    # ------------------------------------------------------------------
    # Empfänger
    # ------------------------------------------------------------------

    @callback
    def async_get_targets(self) -> dict[str, Target]:
        """Alle Geräte der Companion-App, die Push empfangen können."""
        dev_reg = dr.async_get(self.hass)
        targets: dict[str, Target] = {}
        for app_entry in self.hass.config_entries.async_entries(MOBILE_APP_DOMAIN):
            device_name = app_entry.data.get("device_name")
            app_device_id = app_entry.data.get("device_id")
            if not device_name or not app_device_id:
                continue
            service = f"mobile_app_{slugify(device_name)}"
            if not self.hass.services.has_service("notify", service):
                # z. B. Apple Watch: hat keinen eigenen Push-Kanal
                continue
            device = next(
                (
                    dev
                    for dev in dr.async_entries_for_config_entry(
                        dev_reg, app_entry.entry_id
                    )
                    if (MOBILE_APP_DOMAIN, app_device_id) in dev.identifiers
                ),
                None,
            )
            if device is None:
                continue
            targets[device.id] = Target(
                device_id=device.id,
                app_device_id=app_device_id,
                name=device.name_by_user or device.name or device_name,
                notify_service=service,
            )
        return targets

    @callback
    def async_resolve_targets(
        self, persons: list[str] | None, devices: list[str] | None
    ) -> list[Target]:
        """Personen und Geräte in eine Liste von Zielgeräten auflösen.

        Keine Angabe = alle Geräte.
        """
        all_targets = self.async_get_targets()
        if not all_targets:
            raise HomeAssistantError(
                "Keine Geräte mit der Home-Assistant-App gefunden, die "
                "Benachrichtigungen empfangen können."
            )
        if not persons and not devices:
            return list(all_targets.values())

        by_service = {t.notify_service: t for t in all_targets.values()}
        selected: dict[str, Target] = {}

        for device in devices or []:
            target = all_targets.get(device) or by_service.get(device)
            if target is None:
                raise ServiceValidationError(
                    f"Gerät '{device}' ist kein Gerät der Home-Assistant-App "
                    "mit Push-Benachrichtigungen."
                )
            selected[target.device_id] = target

        ent_reg = er.async_get(self.hass)
        for person in persons or []:
            state = self.hass.states.get(person)
            if state is None or not person.startswith("person."):
                raise ServiceValidationError(f"Person '{person}' existiert nicht.")
            found = False
            for tracker in state.attributes.get("device_trackers", []):
                reg_entry = ent_reg.async_get(tracker)
                if reg_entry and reg_entry.device_id in all_targets:
                    selected[reg_entry.device_id] = all_targets[reg_entry.device_id]
                    found = True
            if not found:
                _LOGGER.warning(
                    "Person %s hat kein Gerät mit Push-Benachrichtigungen", person
                )

        if not selected:
            raise ServiceValidationError(
                "Für die angegebenen Empfänger wurde kein Gerät gefunden."
            )
        return list(selected.values())

    # ------------------------------------------------------------------
    # Zentral verwaltete Benachrichtigungen
    # ------------------------------------------------------------------

    def validate_notification(
        self, data: dict[str, Any], original_id: str | None
    ) -> dict[str, Any]:
        """Eingaben prüfen und bereinigen. Wirft ValueError mit deutschem Text."""
        nid = str(data.get(N_ID, "")).strip()
        if original_id is not None:
            nid = original_id  # ID bleibt beim Bearbeiten fest
        elif not nid or slugify(nid) != nid:
            raise ValueError(
                "Die ID darf nur Kleinbuchstaben, Zahlen und _ enthalten "
                "(keine Umlaute oder Leerzeichen)."
            )
        elif nid in self.notifications:
            raise ValueError(f"Die ID „{nid}“ gibt es schon.")

        category = str(data.get(N_CATEGORY, "")).strip()
        if category not in self.types:
            raise ValueError("Bitte eine Kategorie auswählen.")
        message = str(data.get(N_MESSAGE, "")).strip()
        if not message:
            raise ValueError("Der Text darf nicht leer sein.")
        priority = data.get(N_PRIORITY) or PRIORITY_ACTIVE
        if priority not in PRIORITIES:
            raise ValueError(f"Unbekannte Dringlichkeit: {priority}")
        actions = [str(a) for a in data.get(N_ACTIONS) or []]
        unknown = [a for a in actions if a not in self.actions]
        if unknown:
            raise ValueError(f"Unbekannte Knöpfe: {', '.join(unknown)}")
        if len(actions) > 10:
            raise ValueError("Höchstens 10 Knöpfe pro Benachrichtigung.")
        for field_name in (N_TITLE, N_MESSAGE):
            text = str(data.get(field_name) or "")
            if "{" in text:
                try:
                    Environment().parse(text)
                except Exception as err:  # noqa: BLE001 - Jinja-Syntaxfehler
                    raise ValueError(f"Platzhalter im Feld {field_name} fehlerhaft: {err}") from err

        return {
            N_ID: nid,
            N_CATEGORY: category,
            N_TITLE: str(data.get(N_TITLE) or "").strip(),
            N_MESSAGE: message,
            N_PRIORITY: priority,
            N_PERSONS: [str(p) for p in data.get(N_PERSONS) or []],
            N_DEVICES: [str(d) for d in data.get(N_DEVICES) or []],
            N_ACTIONS: actions,
            N_URL: str(data.get(N_URL) or "").strip(),
            N_NOTE: str(data.get(N_NOTE) or "").strip(),
        }

    async def async_save_notification(
        self, data: dict[str, Any], original_id: str | None = None
    ) -> dict[str, Any]:
        """Benachrichtigung anlegen oder ändern (gilt sofort)."""
        if original_id is not None and original_id not in self.notifications:
            raise ValueError(f"Die Benachrichtigung „{original_id}“ gibt es nicht mehr.")
        clean = self.validate_notification(data, original_id)
        self.notifications[clean[N_ID]] = clean
        await self._async_store_notifications()
        return clean

    async def async_delete_notification(self, nid: str) -> None:
        """Benachrichtigung löschen."""
        if self.notifications.pop(nid, None) is None:
            raise ValueError(f"Die Benachrichtigung „{nid}“ gibt es nicht.")
        await self._async_store_notifications()

    async def _async_store_notifications(self) -> None:
        await self._n_store.async_save(
            {"notifications": sorted(self.notifications.values(), key=lambda n: n[N_ID])}
        )
        self.publish_service_schema()

    @callback
    def publish_service_schema(self) -> None:
        """Auswahlliste der IDs im Automations-Editor aktualisieren."""
        base = self.hass.data.get(f"{DOMAIN}_services_yaml") or {}
        send = base.get(SERVICE_SEND)
        if not send or not self.hass.services.has_service(DOMAIN, SERVICE_SEND):
            return
        fields = {k: dict(v) for k, v in (send.get("fields") or {}).items()}
        types = self.types
        options = [
            {
                "value": n[N_ID],
                "label": f"{n[N_ID]} – {n[N_TITLE] or types.get(n[N_CATEGORY], {}).get(CONF_TITLE, n[N_CATEGORY])}",
            }
            for n in sorted(self.notifications.values(), key=lambda n: n[N_ID])
        ]
        if "id" in fields:
            fields["id"]["selector"] = {
                "select": {"options": options, "custom_value": True, "mode": "dropdown"}
            }
        async_set_service_schema(self.hass, DOMAIN, SERVICE_SEND, {"fields": fields})

    @staticmethod
    def _test_priority(priority: str, test: bool) -> str:
        # Ein Test soll nicht mit Alarmton durch Lautlos brechen
        if test and priority == PRIORITY_CRITICAL:
            return PRIORITY_TIME_SENSITIVE
        return priority

    @staticmethod
    def template_variables(*texts: str) -> set[str]:
        """Namen der Platzhalter in den Texten."""
        names: set[str] = set()
        for text in texts:
            if text and "{" in text:
                try:
                    names |= meta.find_undeclared_variables(Environment().parse(text))
                except Exception:  # noqa: BLE001
                    continue
        return names

    def _render(self, text: str, variables: dict[str, Any]) -> str:
        if not text or "{" not in text:
            return text
        try:
            return str(Template(text, self.hass).async_render(variables, parse_result=False))
        except TemplateError as err:
            raise ServiceValidationError(f"Platzhalter konnten nicht gefüllt werden: {err}") from err

    async def async_send_notification(
        self,
        nid: str,
        *,
        persons: list[str] | None = None,
        devices: list[str] | None = None,
        variables: dict[str, Any] | None = None,
        title: str | None = None,
        message: str | None = None,
        priority: str | None = None,
        tag: str | None = None,
        url: str | None = None,
        extra_data: dict[str, Any] | None = None,
        test: bool = False,
    ) -> dict[str, Any]:
        """Zentral verwaltete Benachrichtigung senden.

        Empfänger aus dem Aufruf ersetzen die Standard-Empfänger der Tabelle.
        """
        notification = self.notifications.get(nid)
        if notification is None:
            raise ServiceValidationError(
                f"Benachrichtigung „{nid}“ gibt es nicht. "
                f"Vorhanden: {', '.join(sorted(self.notifications)) or 'keine'}"
            )
        variables = dict(variables or {})
        raw_title = title or notification[N_TITLE]
        raw_message = message or notification[N_MESSAGE]
        if test:
            for name in self.template_variables(raw_title, raw_message):
                variables.setdefault(name, f"‹{name}›")
        if not persons and not devices:
            persons = notification[N_PERSONS] or None
            devices = notification[N_DEVICES] or None
        final_title = self._render(raw_title, variables) if raw_title else None
        if test:
            final_title = f"🧪 {final_title or self.types.get(notification[N_CATEGORY], {}).get(CONF_TITLE, '')}"
        return await self.async_send(
            type_key=notification[N_CATEGORY],
            message=self._render(raw_message, variables),
            title=final_title or None,
            priority=self._test_priority(priority or notification[N_PRIORITY], test),
            persons=persons,
            devices=devices,
            action_keys=list(notification[N_ACTIONS]),
            tag=tag,
            url=url or notification[N_URL] or None,
            extra_data=extra_data,
            force=test,
            source_id=nid,
        )

    # ------------------------------------------------------------------
    # Versand
    # ------------------------------------------------------------------

    def _push_payload(self, priority: str) -> dict[str, Any]:
        opts = self.options
        push: dict[str, Any] = {"interruption-level": priority}
        if priority == PRIORITY_CRITICAL:
            push["sound"] = {
                "name": opts[CONF_CRITICAL_SOUND] or "default",
                "critical": 1,
                "volume": round(float(opts[CONF_CRITICAL_VOLUME]) / 100, 2),
            }
        elif priority == PRIORITY_TIME_SENSITIVE:
            push["sound"] = opts[CONF_TIME_SENSITIVE_SOUND] or "default"
        return push

    @staticmethod
    def _button(nid: str, key: str, action: dict[str, Any]) -> dict[str, Any]:
        button: dict[str, Any] = {
            "action": f"{ACTION_PREFIX}|{nid}|{key}",
            "title": action[CONF_BUTTON_TITLE],
        }
        if action.get(CONF_ICON):
            button["icon"] = f"sfsymbols:{action[CONF_ICON]}"
        if action.get(CONF_AUTH_REQUIRED):
            button["authenticationRequired"] = True
        if action.get(CONF_DESTRUCTIVE):
            button["destructive"] = True
        return button

    async def async_send(
        self,
        *,
        type_key: str,
        message: str,
        title: str | None = None,
        priority: str = PRIORITY_ACTIVE,
        persons: list[str] | None = None,
        devices: list[str] | None = None,
        action_keys: list[str] | None = None,
        tag: str | None = None,
        url: str | None = None,
        extra_data: dict[str, Any] | None = None,
        force: bool = False,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        """Eine Benachrichtigung senden.

        Typ und Aktionen dürfen als Kennung (z. B. haustuer) oder als Gerät aus
        der Auswahlliste angegeben werden.
        """
        type_key = self.resolve_key(type_key, SUBENTRY_TYPE)
        action_keys = [
            self.resolve_key(key, SUBENTRY_ACTION) for key in action_keys or []
        ]
        types = self.types
        if type_key not in types:
            raise ServiceValidationError(
                f"Benachrichtigungstyp '{type_key}' gibt es nicht. "
                f"Vorhanden: {', '.join(sorted(types)) or 'keine'}"
            )
        ntype = types[type_key]

        catalog = self.actions
        action_keys = list(dict.fromkeys(action_keys or []))
        unknown = [key for key in action_keys if key not in catalog]
        if unknown:
            raise ServiceValidationError(
                f"Aktion(en) {', '.join(unknown)} gibt es nicht. "
                f"Vorhanden: {', '.join(sorted(catalog)) or 'keine'}"
            )
        if len(action_keys) > 10:
            raise ServiceValidationError("Maximal 10 Knöpfe pro Benachrichtigung.")

        if priority != PRIORITY_CRITICAL and not force:
            if self.do_not_disturb:
                return {"sent": False, "reason": "do_not_disturb"}
            if type_key in self.muted_types:
                return {"sent": False, "reason": "muted"}

        targets = self.async_resolve_targets(persons, devices)

        nid = uuid.uuid4().hex[:12]
        now = dt_util.utcnow()
        tag = tag or f"nhub-{nid}"
        final_title = title or ntype[CONF_TITLE]

        data: dict[str, Any] = dict(extra_data or {})
        data["push"] = {**data.get("push", {}), **self._push_payload(priority)}
        data["tag"] = tag
        data["group"] = ntype.get(CONF_GROUP) or type_key
        if url:
            data["url"] = url
        if action_keys:
            data["actions"] = [
                self._button(nid, key, catalog[key]) for key in action_keys
            ]

        record_actions: dict[str, Any] = {}
        for key in action_keys:
            minutes = catalog[key].get(CONF_EXPIRY_MINUTES) or 0
            expires = (now + timedelta(minutes=minutes)).isoformat() if minutes else None
            record_actions[key] = {"expires": expires}

        failed: list[str] = []
        for target in targets:
            try:
                await self.hass.services.async_call(
                    "notify",
                    target.notify_service,
                    {"title": final_title, "message": message, "data": data},
                    blocking=True,
                )
            except HomeAssistantError as err:
                _LOGGER.error("Senden an %s fehlgeschlagen: %s", target.name, err)
                failed.append(target.name)

        if len(failed) == len(targets):
            raise HomeAssistantError(
                f"Benachrichtigung konnte an kein Gerät gesendet werden ({', '.join(failed)})."
            )

        self._history[nid] = {
            "sent_at": now.isoformat(),
            "id": source_id,
            "type": type_key,
            "title": final_title,
            "message": message,
            "priority": priority,
            "tag": tag,
            "targets": [t.device_id for t in targets],
            "recipients": [t.name for t in targets],
            "actions": record_actions,
            "handled": None,
        }
        self._prune()
        self._schedule_save()

        self.last_sent = {
            "notification_id": nid,
            "sent_at": now,
            "id": source_id,
            "type": type_key,
            "title": final_title,
            "message": message,
            "priority": priority,
            "recipients": [t.name for t in targets],
            "actions": action_keys,
        }
        async_dispatcher_send(self.hass, SIGNAL_SENT)

        return {
            "sent": True,
            "notification_id": nid,
            "tag": tag,
            "recipients": [t.name for t in targets],
            "failed": failed,
        }

    async def async_clear(
        self,
        tag: str,
        persons: list[str] | None = None,
        devices: list[str] | None = None,
    ) -> None:
        """Benachrichtigung mit diesem Tag von den Geräten entfernen."""
        targets = self.async_resolve_targets(persons, devices)
        await self._async_clear_on(targets, tag)

    async def _async_clear_on(self, targets: list[Target], tag: str) -> None:
        for target in targets:
            try:
                await self.hass.services.async_call(
                    "notify",
                    target.notify_service,
                    {"message": "clear_notification", "data": {"tag": tag}},
                    blocking=True,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Entfernen auf %s fehlgeschlagen: %s", target.name, err)

    async def _async_feedback(self, targets: list[Target], message: str) -> None:
        for target in targets:
            try:
                await self.hass.services.async_call(
                    "notify",
                    target.notify_service,
                    {
                        "title": "Benachrichtigungszentrale",
                        "message": message,
                        "data": {"push": {"interruption-level": PRIORITY_PASSIVE}},
                    },
                    blocking=True,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("Rückmeldung an %s fehlgeschlagen: %s", target.name, err)

    # ------------------------------------------------------------------
    # Knopfdrücke
    # ------------------------------------------------------------------

    @callback
    def async_handle_event(self, event: Event) -> None:
        """Ereignis der Mobile App verarbeiten (nur eigene Knöpfe)."""
        action_id = event.data.get("action")
        if not isinstance(action_id, str) or not action_id.startswith(
            f"{ACTION_PREFIX}|"
        ):
            return
        self.hass.async_create_task(
            self.async_handle_action(action_id, dict(event.data)),
            eager_start=True,
        )

    async def async_handle_action(self, action_id: str, event_data: dict[str, Any]) -> str:
        """Knopfdruck ausführen. Gibt das Ergebnis als Text zurück."""
        parts = action_id.split("|")
        if len(parts) != 3:
            _LOGGER.warning("Ungültige Knopf-ID: %s", action_id)
            return "invalid"
        _, nid, key = parts

        all_targets = self.async_get_targets()
        source = next(
            (
                t
                for t in all_targets.values()
                if t.app_device_id == event_data.get("sourceDeviceID")
            ),
            None,
        )
        feedback_targets = [source] if source else []

        record = self._history.get(nid)
        if record is None or key not in record["actions"]:
            _LOGGER.warning("Knopfdruck zu unbekannter Benachrichtigung: %s", action_id)
            if self.options[CONF_EXPIRED_FEEDBACK] and feedback_targets:
                await self._async_feedback(
                    feedback_targets,
                    "Diese Benachrichtigung ist nicht mehr bekannt. Aktion nicht ausgeführt.",
                )
            self._fire(nid, key, None, "unknown", source)
            return "unknown"

        record_targets = [all_targets[d] for d in record["targets"] if d in all_targets]
        if not feedback_targets:
            feedback_targets = record_targets
        action = self.actions.get(key)
        title = action[CONF_BUTTON_TITLE] if action else key

        if record.get("handled"):
            _LOGGER.info("Benachrichtigung %s wurde bereits bearbeitet", nid)
            self._fire(nid, key, record, "already_handled", source)
            return "already_handled"

        expires = record["actions"][key].get("expires")
        if expires and dt_util.utcnow() > dt_util.parse_datetime(expires):
            if self.options[CONF_EXPIRED_FEEDBACK]:
                await self._async_feedback(
                    feedback_targets,
                    f"Die Aktion „{title}“ ist abgelaufen und wurde nicht ausgeführt.",
                )
            self._fire(nid, key, record, "expired", source)
            return "expired"

        if action is None:
            await self._async_feedback(
                feedback_targets,
                f"Die Aktion „{key}“ gibt es nicht mehr. Nichts ausgeführt.",
            )
            self._fire(nid, key, record, "unknown_action", source)
            return "unknown_action"

        try:
            await self._async_execute(action)
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.error("Aktion %s fehlgeschlagen: %s", key, err)
            await self._async_feedback(
                feedback_targets, f"Die Aktion „{title}“ ist fehlgeschlagen: {err}"
            )
            self._fire(nid, key, record, "failed", source)
            return "failed"

        record["handled"] = {
            "action": key,
            "at": dt_util.utcnow().isoformat(),
            "device": source.device_id if source else None,
        }
        self._schedule_save()
        await self._async_clear_on(record_targets, record["tag"])
        self._fire(nid, key, record, "executed", source)
        return "executed"

    async def _async_execute(self, action: dict[str, Any]) -> None:
        domain, _, service = action[CONF_SERVICE].partition(".")
        if not domain or not service:
            raise ValueError(f"Ungültiger Dienst: {action[CONF_SERVICE]}")
        service_data = dict(action.get(CONF_SERVICE_DATA) or {})
        entities = action.get(CONF_TARGET_ENTITIES) or []
        target = {"entity_id": list(entities)} if entities else None
        await self.hass.services.async_call(
            domain,
            service,
            service_data,
            blocking=True,
            target=target,
        )

    @callback
    def _fire(
        self,
        nid: str,
        key: str,
        record: dict[str, Any] | None,
        result: str,
        source: Target | None,
    ) -> None:
        self.hass.bus.async_fire(
            EVENT_ACTION,
            {
                "notification_id": nid,
                "action": key,
                "action_title": (
                    self.actions.get(key, {}).get(CONF_BUTTON_TITLE, key)
                ),
                "type": record["type"] if record else None,
                "result": result,
                "device_id": source.device_id if source else None,
                "device_name": source.name if source else None,
            },
        )
