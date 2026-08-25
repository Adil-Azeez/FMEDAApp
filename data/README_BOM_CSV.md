# BOM CSV Format Documentation

The FMEDA application imports BOM components from CSV files using the following specifications.

## Delimiters & Encodings
- **Delimiters**: Both comma (`,`) and semicolon (`;`) delimiters are automatically detected.
- **Encoding**: Standard UTF-8 and UTF-8 with BOM (`utf-8-sig`) are supported.

## Columns & Headers
Only `designator` is required. All other columns are optional. Headers are case-insensitive and can have leading or trailing whitespace.

### Mapped Fields and Common Aliases
*   **Designator** (Required):
    *   `designator`, `component`, `component_id`, `position`, `pos`, `bauteil`, `reference`, `refdes`
*   **Function**:
    *   `function`, `funktion`
*   **Value**:
    *   `value`, `wert`
*   **Description**:
    *   `description`, `beschreibung`, `value_description`, `value / description`, `wert / beschreibung`
*   **Internal Part Number**:
    *   `internal_part_number`, `part_number`, `internal_pn`, `material_number`, `teilenummer`, `tn`
*   **Manufacturer**:
    *   `manufacturer`, `hersteller`
*   **Manufacturer Part Number**:
    *   `manufacturer_part_number`, `manufacturer_pn`, `herstellerteilenummer`
*   **Layer**:
    *   `layer`, `lage`
*   **Location**:
    *   `location`, `ort`
*   **Fitted Status**:
    *   `fitted`, `fitted_status`, `status`, `bestückt`, `bestueckt`
*   **Notes**:
    *   `notes`, `note`, `comments`, `bemerkung`, `bemerkungen`

## Fitted Value Normalization
*   **Fitted = True**: `true`, `yes`, `1`, `fitted`, `bestückt`, `bestueckt`, or empty cell.
*   **Fitted = False**: `false`, `no`, `0`, `not fitted`, `not_fitted`, `nicht bestückt`, `nicht bestueckt`, `dnp`, `do not populate`.
*   *Values are matched ignoring surrounding whitespace and capitalization.*
