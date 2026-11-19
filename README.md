

# Arbeitszeitgesetz für Odoo
<!-- /!\ Non OCA Context : Set here the badge of your runbot / runboat instance. -->
[![Pre-commit Status](https://github.com/BM1-de/odoo-l10n-germany-arbzg/actions/workflows/pre-commit.yml/badge.svg?branch=19.0)](https://github.com/BM1-de/odoo-l10n-germany-arbzg/actions/workflows/pre-commit.yml?query=branch%3A19.0)
[![Build Status](https://github.com/BM1-de/odoo-l10n-germany-arbzg/actions/workflows/test.yml/badge.svg?branch=19.0)](https://github.com/BM1-de/odoo-l10n-germany-arbzg/actions/workflows/test.yml?query=branch%3A19.0)
[![codecov](https://codecov.io/gh/BM1-de/odoo-l10n-germany-arbzg/branch/19.0/graph/badge.svg)](https://codecov.io/gh/BM1-de/odoo-l10n-germany-arbzg)
<!-- /!\ Non OCA Context : Set here the badge of your translation instance. -->

<!-- /!\ do not modify above this line -->

Pausen und Höchstarbeitszeit nach dem Arbeitszeitgesetz (ArbZG) direkt in den
Anwesenheiten von Odoo 19: Fehlt die gesetzliche Pause, wird sie eingefügt oder angezeigt,
über 10 Stunden Arbeit am Tag bekommen Mitarbeiter und Zuständige eine Meldung, und ein
vergessenes Ausstempeln endet bei der Höchstarbeitszeit.

> **Alpha:** Die Regeln laufen so seit September 2026 bei der Baumgärtner Marketing GmbH,
> als Modul sind sie neu. Das Modul ersetzt keine Rechtsberatung; die Software wird ohne
> Gewährleistung bereitgestellt (AGPL-3.0, Abschnitte 15 und 16).

![Fehlende Pause in der Mitte der längsten Anwesenheit eingefügt](docs/screenshots/pause-eingefuegt.png)

## Was das Modul tut

- **Pausen (§ 4 ArbZG):** über 6 Stunden Arbeit am Tag 30 Minuten, über 9 Stunden 45
  Minuten. Lücken ab 15 Minuten zählen als Pause, ebenso die Pausen des Arbeitszeitplans,
  die Odoo abzieht. Verlangt wird nur die Zeit über der Grenze: 6:10 Stunden brauchen
  10 Minuten Pause.
- **Fehlende Pause:** Sie wird in die Mitte der längsten Anwesenheit des Tages gelegt und
  dort vermerkt – oder nur angezeigt, mit einer Nachricht an den Mitarbeiter.
- **Höchstarbeitszeit (§ 3 ArbZG):** Mehr als 10 Stunden Arbeit am Tag werden nicht
  gekürzt, weil die Aufzeichnung die tatsächliche Zeit zeigen muss (§ 16 Abs. 2 ArbZG).
  Der Mitarbeiter bekommt eine Nachricht, die zuständige Person eine Aufgabe, einmal je
  Tag.
- **Vergessenes Ausstempeln:** Eine geplante Aktion stempelt alle 15 Minuten aus, wer die
  Höchstarbeitszeit des Tages erreicht hat.
- **Korrekturen:** Jede Änderung prüft den ganzen Tag neu. Wer eine eingefügte Pause
  entfernt, bekommt sie zurück; wer später eine kürzere echte Pause einträgt, bekommt nur
  den Rest ergänzt.
- **Ausnahmen:** Auftragnehmer und Freiberufler sowie markierte Mitarbeiter, etwa
  Geschäftsführer und leitende Angestellte (§ 18 ArbZG), werden nicht geprüft.

Alle Grenzen sind je Firma einstellbar, falls sich das Gesetz ändert.

## Einrichtung

1. Unter *Apps* „Germany Working Time Act“ installieren; das Modul braucht die App
   *Anwesenheiten*.
2. *Anwesenheiten → Konfiguration → Einstellungen*, Block *Arbeitszeitgesetz
   (Deutschland)*: Grenzen prüfen, „Fehlende Pause einfügen“ oder „nur anzeigen“ wählen
   und festlegen, wer bei überschrittener Höchstarbeitszeit eine Aufgabe bekommt (leer:
   der Genehmiger der Anwesenheiten).
3. Am Mitarbeiter, neben dem Genehmiger der Anwesenheiten: „Nicht unter dem
   Arbeitszeitgesetz“ für Geschäftsführer und leitende Angestellte.

![Einstellungen zum Arbeitszeitgesetz](docs/screenshots/einstellungen.png)

## Im Alltag

- Pausen am besten stempeln (Abmelden, Anmelden) oder beim Nachtragen als Lücke eintragen.
  Die Regel ist nur das Netz.
- Im Modus „nur anzeigen“ zeigt die Spalte *Fehlende Pause (Minuten)* der
  Anwesenheitsliste, wo etwas fehlt.

![Anwesenheiten mit eingefügten Pausen](docs/screenshots/liste.png)

## Grenzen

- Geprüft wird die Summe der Pausen am Tag, nicht die sechs Stunden „hintereinander“ aus
  § 4 Satz 3 ArbZG.
- Nicht geprüft werden die Ruhezeit (§ 5), Sonn- und Feiertage (§§ 9–11), Nachtarbeit
  (§ 6), die Wochenarbeitszeit, der Jugendarbeitsschutz und tarifliche Abweichungen (§ 7).

## Mehr Dokumentation

Die Beschreibung des Moduls (englisch) steht in
[l10n_de_hr_attendance_arbzg/README.rst](l10n_de_hr_attendance_arbzg/README.rst).

*English: Legal breaks and the daily maximum working time of the German Working Time Act
(ArbZG) for the attendances of Odoo 19: missing breaks are inserted or pointed out, more
than 10 hours of work a day are reported, forgotten check-outs end at the maximum. Alpha,
no legal advice, no warranty.*

<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)

Available addons
----------------
addon | version | maintainers | summary
--- | --- | --- | ---
[l10n_de_hr_attendance_arbzg](l10n_de_hr_attendance_arbzg/) | 19.0.1.0.0 | <a href='https://github.com/bm1-phillip'><img src='https://github.com/bm1-phillip.png' width='32' height='32' style='border-radius:50%;' alt='bm1-phillip'/></a> | Legal breaks and the daily maximum of the German Working Time Act (ArbZG) for attendances

[//]: # (end addons)

<!-- prettier-ignore-end -->

## Licenses

This repository is licensed under [AGPL-3.0](LICENSE).

However, each module can have a totally different license, as long as they adhere to Baumgärtner Marketing GmbH
policy. Consult each module's `__manifest__.py` file, which contains a `license` key
that explains its license.

----
<!-- /!\ Non OCA Context : Set here the full description of your organization. -->

<!-- bm1-verweise:start (scripts/readme-bm1.py, nicht von Hand ändern) -->

## Weitere Odoo-Projekte von BM1

| Projekt | Zweck |
| ------- | ----- |
| [Cc und Bcc](https://github.com/BM1-de/odoo-mail-cc-bcc) | Cc und Bcc beim Mailversand, eine einzige E-Mail an alle Empfänger |
| [Briefanrede](https://github.com/BM1-de/odoo-partner-salutation) | Anrede am Kontakt und die passende Grußzeile in Rechnungsmails |
| [Namenszusatz](https://github.com/BM1-de/odoo-partner-name-addition) | Zweite Namenszeile am Kontakt, gedruckt in jeder Anschrift |
| [Stundennachweis auf der Rechnung](https://github.com/BM1-de/odoo-timesheet-invoice) | Abgerechnete Zeiteinträge auf der Rechnung, je Aufgabe summiert |
| [Deutsche EÜR](https://github.com/BM1-de/odoo-l10n-germany-euer) | Einnahmenüberschussrechnung mit Anlage EÜR, AVEÜR und Anlagenverzeichnis |
| [Papierkram-Import](https://github.com/BM1-de/odoo-papierkram-import) | Kontakte, Rechnungen, Belege, Zahlungen und Zeiten aus Papierkram übernehmen |
| [Zeiterfassung für Odoo (macOS)](https://github.com/BM1-de/timesheets-for-odoo) | Menüleisten-App für Zeiten und Anwesenheit |
| [Zeiterfassung für Odoo (Windows)](https://github.com/BM1-de/timesheets-for-odoo-windows) | App im Infobereich für Zeiten und Anwesenheit |

## Über BM1

<a href="https://bm1.de"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/bm1/logo-bm1-negativ.svg"><img src="docs/bm1/logo-bm1.svg" alt="BM1" width="180"></picture></a>

Entwickelt und gepflegt von [BM1](https://bm1.de), der Baumgärtner Marketing GmbH aus
Bayreuth: Agentur für [Websites](https://bm1.de/websites/),
[Webentwicklung](https://bm1.de/webentwicklung/), [SEO](https://bm1.de/seo/) und
[individuelle digitale Lösungen](https://bm1.de/digitale-spezial-themen/). Wir arbeiten selbst
jeden Tag mit Odoo und bauen, was uns dort fehlt. Wenn Sie Unterstützung bei Odoo, einer
Website oder einer Anbindung brauchen, die es nicht von der Stange gibt:
[sprechen Sie uns an](https://bm1.de/kontakt/).

<!-- bm1-verweise:end -->
