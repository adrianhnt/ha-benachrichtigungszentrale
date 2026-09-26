# Benachrichtigungszentrale

Home-Assistant-Integration für Push-Benachrichtigungen an die Companion-App (iOS).

## Seite „Benachrichtigungen“

Eigene Seite in der Seitenleiste (nur für Administratoren) mit vier Tabellen:

- **Benachrichtigungen** – jede Zeile eine fertige Benachrichtigung: ID, Kategorie, Titel, Text (mit Platzhaltern wie `{{ dauer }}`), Dringlichkeit, Standard-Empfänger, Knöpfe, Notiz. „Verwendet in“ zeigt, welche Automationen und Skripte die ID aufrufen – und darunter, was ein Aufruf gegenüber der Tabelle überschreibt (z. B. „Dringlichkeit → Standard“). Test senden und Aufruf kopieren direkt aus der Tabelle. Ein Test wird genau wie aus einer Automation gesendet, nur mit 🧪 vor dem Titel.
- **Knöpfe** – wiederverwendbare Aktionsknöpfe: Text, SF-Symbol, Gültigkeit, Face ID, rot – und beliebig viele Schritte (je Aktion + Entitäten + optionale Daten), die beim Tippen der Reihe nach ausgeführt werden.
- **Kategorien** – ordnen Benachrichtigungen, stapeln sie auf dem iPhone und lassen sich gemeinsam stummschalten (kritische kommen immer durch).
- **Geräte** – Lautstärke kritischer Benachrichtigungen pro Gerät (auch als Entität `number.…_kritische_lautstarke_…` für Automationen).

Änderungen gelten sofort beim nächsten Senden.

## In Automationen

```yaml
action: notification_hub.send
data:
  id: waesche_fertig
  variables:
    dauer: "1:32 h"
```

- `id` wählt die Benachrichtigung (im Editor als Auswahlliste).
- `persons` / `devices` sind optional und **ersetzen** die Standard-Empfänger der Tabelle.
- `title`, `message`, `priority` überschreiben bei Bedarf die Werte aus der Tabelle.
- Die bisherige Variante ohne `id` (mit `type`, `message`, `actions`) funktioniert weiter.

Jeder Knopfdruck löst das Ereignis `notification_hub_action` aus und erscheint im Logbuch.

## Installation

HACS → ⋮ → *Benutzerdefinierte Repositories* → dieses Repository als *Integration* hinzufügen → herunterladen → Home Assistant neu starten → Integration „Benachrichtigungszentrale“ hinzufügen.
