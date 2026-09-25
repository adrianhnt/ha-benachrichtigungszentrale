# Benachrichtigungszentrale

Home-Assistant-Integration für Push-Benachrichtigungen an die Companion-App (iOS).

- **Benachrichtigungstypen** (Titel, Gruppierung) und **Aktionen** (Knöpfe) werden in der Oberfläche verwaltet: *Einstellungen → Geräte & Dienste → Benachrichtigungszentrale*.
- Versand über den Dienst `notification_hub.send`: Typ, Nachricht, Dringlichkeit (passiv, Standard, zeitkritisch, kritisch), Empfänger (Personen und/oder Geräte, leer = alle), Knöpfe.
- Typ und Aktionen lassen sich im Automations-Editor aus einer Liste auswählen; in YAML gehen auch die Kennungen.
- Knöpfe können verfallen (Gültigkeit pro Aktion, bis 30 Tage), Face ID verlangen und werden nach dem Ausführen auf allen Geräten entfernt.
- Schalter „Nicht stören“ (global) und „Stumm“ (pro Typ); kritische Benachrichtigungen kommen immer durch.
- Jeder Knopfdruck löst das Ereignis `notification_hub_action` aus und erscheint im Logbuch.

## Installation

HACS → ⋮ → *Benutzerdefinierte Repositories* → dieses Repository als *Integration* hinzufügen → herunterladen → Home Assistant neu starten → Integration „Benachrichtigungszentrale“ hinzufügen.

## Beispiel

```yaml
action: notification_hub.send
data:
  type: haustuer
  priority: active
  message: Auto Open ist noch eingeschaltet.
  actions:
    - auto_open_aus
```
# ha-benachrichtigungszentrale
Benachrichtigungszentrale – Home-Assistant-Integration für Push-Benachrichtigungen an die Companion-App
