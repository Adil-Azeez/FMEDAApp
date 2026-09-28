# BOM Fixed-Width Text Format Documentation

The FMEDA application imports BOM components from fixed-width text files (*.txt) using the following specifications.

## Structure and Header Detection
Fixed-width column boundaries are determined automatically by locating the header row containing standard column designations.

### Supported Columns
- **Vs**: Version / Status revision code
- **Pos** (Required): Component Position / Designator (e.g. C3, R101)
- **MN**: Material Number / Internal Part Number (e.g. 00123456)
- **Benennung**: Component classification / designation (e.g. KERAMIK-KONDENSATOR, WIDERSTAND)
- **Wert**: Component value (e.g. 100n, 10k, 1uF)
- **Beschreibung**: Component engineering description (e.g. CAP-VS 100nF/16V 0201)
- **Bemerkung**: Remarks / Notes (e.g. SMD, nicht bestueckt)
- **Lage**: Assembly layer / PCB side (e.g. TOP, BOT)

## Ignored Elements
- Document header metadata, dates, project numbers, authors
- Revision history tables and change logs
- Dashed separator lines (----, ====)
- Blank lines and whitespace-only lines
- Comment lines (//, /*, --, #)
- Page headers and footers (Seite 1 von 5, Page 1 of 3)
- LIST END markers

## Value / Description Rule
In the FMEDA spreadsheet, the combined Value / Description field is filled using:
Wert + ' / ' + Beschreibung
- If both are present: Wert / Beschreibung
- If only Wert is present: Wert
- If only Beschreibung is present: Beschreibung
- If both are absent: Empty string

## Not-Fitted Components
If Bemerkung contains nicht bestueckt (or nicht bestueckt, dnp, not fitted), the component is marked as Not Fitted and excluded from active FMEDA safety channel calculations.
