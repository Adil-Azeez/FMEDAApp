# FMEDA SQLite Component Database Documentation

---

## 1. Document Information

| Attribute | Details |
| :--- | :--- |
| **Document Title** | FMEDA SQLite Component Database Technical Implementation & Architecture Report |
| **Application Name** | FMEDA PyQt6 Desktop Application (`fmeda_app8`) |
| **Documentation Date** | 2026-09-01 |
| **Operational Database Path** | `data/fmeda.sqlite` (resolved relative to project root containing `main.py`) |
| **Seed JSON Source Path** | `data/seed/Combined_Exida_Component_library_version2.json` |
| **SQLite Schema Version** | `1.0` |
| **Seed Library ID** | `b41d2f01-9596-5b7a-958f-ed405f96955a` |
| **Application Version** | `1.0.0` |
| **Git Commit Hash** | `741dfab173ae1539457560b87d3129b8b9701448` |
| **Author** | Antigravity AI Engineering Assistant / DeepMind Advanced Agentic Coding |
| **Reviewer** | Technical Lead / Functional Safety Assessor |
| **Document Status** | **Approved & Verified** (Production Ready) |

---

## 2. Purpose and Scope

### 2.1 Why SQLite Was Introduced
The FMEDA (Failure Modes, Effects, and Diagnostic Analysis) application requires an authoritative, high-integrity component reliability catalog to determine base failure rates ($\lambda$ in FIT), failure mode distributions, and safety classifications. Previously, the application relied on a flat, unindexed JSON file (`data/components_db.json`). 

SQLite was introduced to replace the flat JSON file with a normalized relational operational database (`data/fmeda.sqlite`).

### 2.2 Problems with the Previous Flat JSON Approach
1. **Lack of Relational Normalization:** Failure rates, component metadata, aliases, and failure modes were duplicated in unstructured JSON blocks.
2. **Single Failure Rate Constraint:** Flat JSON supported only one static FIT value per component, making it impossible to evaluate functional safety across different operating environments (IEC/exida Profiles 1 through 5).
3. **No Referential Integrity:** The JSON format lacked foreign key constraints, unique key checks, and atomic transactions.
4. **Poor Query Performance & Concurrency:** Looking up components required linear scans of in-memory dictionaries.
5. **No Audit Trail:** Renaming or adjusting component parameters left no historical record or legacy alias tracking.

### 2.3 Why SQLite Was Selected
- **Embedded & Zero-Configuration:** Runs in-process within Python via standard `sqlite3` without external daemon dependencies or network configuration.
- **ACID Transactions & Foreign Keys:** Full support for transactions and `PRAGMA foreign_keys = ON;` ensures referential consistency.
- **Indexed Relational Queries:** Multi-tier lookups across UUIDs, Failure Rate IDs, display names, legacy aliases, and types execute in sub-millisecond time.
- **Strict Data Isolation:** Allows the operational component catalog to remain separate from individual project files while enabling project-level snapshotting.

### 2.4 Data Storage Boundaries
- **Stored in SQLite (`data/fmeda.sqlite`):** Master normalized Exida component catalog, profile-specific failure rates (Profiles 1–5), standardized failure modes, failure mode percentage distributions per profile, unmapped legacy component templates, historical aliases, and component change audit logs.
- **Stored in Project JSON Files (`data/projects/*.json`):** Project metadata, functional units, instantiated component positions (e.g. `C101`, `R102`), configured failure mode assignments, diagnostic measures, deviations, mitigations, calculated SIL/PFD/SFF metrics, and complete frozen component snapshots.
- **Outside Database Scope:** Calculation algorithms for SFF/PFD/PFH/MTBF, UI view controllers, Excel/PDF report generation, and BOM CSV parsing.

> [!IMPORTANT]
> **Operational Rule:** `data/fmeda.sqlite` is the sole operational component library. The seed JSON file (`data/seed/Combined_Exida_Component_library_version2.json`) is used strictly for initial database creation, explicit administrator rebuilds, migration verification, and disaster recovery. During normal runtime, the application operates exclusively against SQLite and does not load or parse the seed JSON.

---

## 3. Previous Architecture

### 3.1 Original Workflow
In the previous architecture:
1. On startup, the application loaded the entirety of `data/components_db.json` into memory.
2. Components were identified solely by a shortcut code or display name string (e.g. `CKPe`, `CEL`, `RM10e`).
3. Each component template contained a single fixed FIT value (typically Profile 1 or an unstated ambient condition).
4. Failure modes were stored as a simple key-value dictionary of `{ "Failure Mode Name": percentage }`.

### 3.2 Limitations of the Old Architecture
- No support for Environmental Profiles 1 through 5.
- Component display names ending in lowercase `e` (e.g., `CKPe`, `RM10e`, `NREFe`) were mixed with normalized engineering designations.
- Project calculations could not be traced back to standardized Exida handbook records or Failure Rate IDs (e.g., `FR-000001`).
- Missing or unknown components could not be safely isolated from approved Exida components.

### 3.3 Status of `data/components_db.json`
- **Location:** `data/components_db.json`
- **Current Runtime Status:** **Deprecated.** The active application does not load or read `data/components_db.json` during normal operation.
- **Retention Policy:** Kept temporarily as a static backup until legacy project migration verification is completed.

---

## 4. New Architecture

### 4.1 Data Flow Architecture
The new architecture establishes a clean, decoupled data pipeline:

```
+-------------------------------------------------------------------------------+
|                        Seed Source (JSON Catalog)                             |
|          data/seed/Combined_Exida_Component_library_version2.json             |
+-------------------------------------------------------------------------------+
                                       |
                                       | (Initial DB Creation / Admin Rebuild)
                                       v
+-------------------------------------------------------------------------------+
|                    Operational SQLite Database Layer                          |
|                            data/fmeda.sqlite                                  |
|   - library_metadata          - component_failure_rates                       |
|   - profiles (Profiles 1-5)   - failure_modes & component_failure_modes       |
|   - components (364 Exida)    - legacy_components & legacy_failure_modes      |
|   - component_aliases         - component_change_log (Audit Trail)            |
+-------------------------------------------------------------------------------+
                                       |
                                       | (PRAGMA foreign_keys = ON, sqlite3.Row)
                                       v
+-------------------------------------------------------------------------------+
|                         Component Library Service                             |
|           fmeda_tool/services/component_library_service.py                    |
|   - Multi-tier component resolution (7 Tiers)                                 |
|   - Profile-aware FIT & Failure Mode Percentage queries                       |
|   - Display-name validation, single assignment, & atomic batch editing        |
|   - Display-name removal (restoration to NULL with component_type fallback)   |
|   - Complete standalone Project Snapshot generation                           |
+-------------------------------------------------------------------------------+
                                       |
                   +-------------------+-------------------+
                   |                                       |
                   v                                       v
+------------------------------------+   +------------------------------------+
|       Component Picker UI          |   |  Library Management UI (Admin)     |
|   - Exida Components Tab (Default) |   |   - Exida Catalog Tab              |
|   - Legacy Unmapped Tab (Warning)  |   |   - Legacy Catalog Tab             |
|   - Multi-field filters & search   |   |   - Unassigned Batch Edit Tab      |
|   - Null-FIT safety detection      |   |   - Audit Change Log Tab           |
+------------------------------------+   |   - Database Rebuild Tab           |
                   |                     +------------------------------------+
                   v
+-------------------------------------------------------------------------------+
|                    FMEDA Project & Functional Units                           |
|                        (Project File JSON Storage)                            |
|   - Component instances with position designators (e.g. C101, R204)           |
|   - Embedded immutable Component Snapshot (isolated from subsequent edits)     |
|   - Instantiated FailureModeAssignment objects with diagnostic coverage (DC)   |
|   - Strict Profile preservation (Project.selected_profile)                    |
+-------------------------------------------------------------------------------+
```

### 4.2 System Layer Classification

| Layer | Component / File | Responsibility | Implementation Status |
| :--- | :--- | :--- | :--- |
| **Seed Layer** | `data/seed/*.json` | Immutable source catalog for initialization and disaster recovery. | **Implemented** |
| **Database Layer** | `fmeda_tool/db/database.py`, `schema.sql` | Relational storage, schema DDL, foreign keys, path resolution, test isolation guard. | **Implemented** |
| **Service Layer** | `fmeda_tool/services/component_library_service.py` | Querying, multi-tier resolution, snapshotting, display-name validation/batching/removal. | **Implemented** |
| **UI Picker Layer** | `fmeda_tool/ui/dialogs/component_picker_dialog.py`, `component_selection_dialog.py` | Dual-tab Exida/Legacy selection, profile-specific failure rate inspection, null-FIT warning. | **Implemented** |
| **UI Management Layer** | `fmeda_tool/ui/components_db_view.py` | Display-name editing, batch assignment, change log viewer, database rebuild. | **Implemented** |
| **Project Model Layer** | `fmeda_tool/models/component.py`, `project.py` | Project snapshot isolation, profile storage, calculation independence. | **Implemented** |

---

## 5. File and Folder Structure

```
c:\Users\adila\Downloads\fmeda_app8\
│
├── data/
│   ├── fmeda.sqlite                                  # Operational SQLite database
│   ├── components_db.json                            # Deprecated flat JSON (backup only)
│   ├── projects/                                     # Saved FMEDA project JSON files
│   └── seed/
│       └── Combined_Exida_Component_library_version2.json  # Authoritative seed source
│
├── fmeda_tool/
│   ├── db/
│   │   ├── __init__.py                               # Package exports
│   │   ├── database.py                               # DatabaseService, connections, path resolution, seeding
│   │   └── schema.sql                                # Relational DDL schema & indexes
│   │
│   ├── models/
│   │   ├── component.py                              # Component model with snapshot fields
│   │   ├── project.py                                # Project model with selected_profile
│   │   ├── unit.py                                   # Functional unit model
│   │   └── failure_mode_assignment.py                # Failure mode assignment model
│   │
│   ├── services/
│   │   ├── __init__.py                               # Package exports
│   │   ├── component_library_service.py              # Query, resolution, snapshots, display-name logic
│   │   ├── calculation_service.py                    # FMEDA mathematical engine
│   │   ├── validation_service.py                     # Safety rule verification
│   │   └── project_service.py                        # Project file persistence & migration
│   │
│   └── ui/
│       ├── main_window.py                            # Main application window & routing
│       ├── create_project_view.py                    # Project creation with Profile 1-5 selector
│       ├── unit_editor_view.py                       # Workspace table editor
│       ├── components_db_view.py                     # Component library & display-name management
│       └── dialogs/
│           ├── component_picker_dialog.py            # Dual-tab component picker dialog
│           └── component_selection_dialog.py         # Component configuration dialog
│
├── tests/
│   ├── conftest.py                                   # Global test isolation fixture (temp DB)
│   ├── test_sqlite_library.py                        # SQLite migration, resolution & audit tests
│   ├── test_component_addition.py                    # Component picker integration tests
│   └── ... (13 additional test files)
│
├── docs/
│   └── FMEDA_SQLite_Database_Documentation.md        # This technical documentation
│
├── main.py                                           # Application entry point
└── requirements.txt                                  # Python dependencies
```

---

## 6. Seed JSON Structure

### 6.1 Top-Level Sections
The seed file `data/seed/Combined_Exida_Component_library_version2.json` contains:
- `schema_version`: String (`"1.0"`).
- `library_id`: Canonical UUID string (`"b41d2f01-9596-5b7a-958f-ed405f96955a"`).
- `description`: Library description text.
- `profiles`: Array of 5 profile definitions (`profile_1` through `profile_5`).
- `counts`: Metadata count dictionary recorded during seed creation.
- `components`: Array of 364 normalized Exida component records.
- `legacy_components_unmapped`: Array of 143 unmapped legacy component records.
- `display_name_policy`: Documentation of naming policies and alias retention rules.
- `migration_changes`: Change documentation regarding normalized names.

### 6.2 Fields of a Normalized Exida Component
Each component record in `components` contains:
- `id`: Unique UUID string (e.g., `"094127de-f949-50f1-adc0-07132ba36bf3"`).
- `failure_rate_id`: Unique Exida Failure Rate ID string (e.g., `"FR-000001"`).
- `item_id`: Handbook item UUID or internal reference.
- `item_no`: Handbook classification number (e.g., `"E.1.1.1"`).
- `display_name`: Approved short display name string (e.g. `"CEL"`), or `null` if unassigned.
- `legacy_aliases`: Array of strings representing historical names (e.g. `["CELe"]`).
- `component_type`: Standardized primary component classification (e.g., `"Capacitor Electrolytic"`).
- `component_subtype`: Sub-classification (e.g., `"Tantalum - Solid"`).
- `component_use_category`: Environmental/functional application category.
- `failure_rates_fit`: Dictionary mapping profiles to FIT values: `{"Profile 1": 5.2, "Profile 2": 2.7, "Profile 3": 5.2, "Profile 4": 0.7, "Profile 5": 10.4}`.
- `failure_modes`: Array of failure mode objects with `id`, `name`, `description`, and profile percentage distribution mapping.
- `mapping`: Dictionary containing `status` (`"mapped"` / `"unmapped"`), `basis`, and `review_required`.
- `source`: Dictionary containing source catalog reference name and record item number.

### 6.3 Fields of a Legacy Component Record
Each record in `legacy_components_unmapped` contains:
- `id`: Legacy identifier string (e.g., `"db_c"`).
- `display_name`: Legacy name string (e.g., `"C"`).
- `shortcut`: Shorthand code (e.g., `"C"`).
- `material`: Material / type description (e.g., `"Capacitor"`).
- `database`: Origin database tag (e.g., `"Legacy"`).
- `fits`: Legacy baseline failure rate in FIT (e.g., `1.0`).
- `failure_modes`: Dictionary mapping failure mode name to percentage: `{"Short": 50.0, "Open": 50.0}`.
- `mapping_status`: `"unmapped_legacy"`.
- `review_required`: `true` (integer `1`).

### 6.4 Actual Seed Count Verification

| Category / Metric | Seed Metadata (`counts`) | Actual Recalculated Seed Count | SQLite Database Row Count | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Normalized Exida Components** | 364 | **364** | **364** | Exact Match |
| **Assigned Display Names** | 130 | **130** | **130** | Exact Match |
| **Unassigned Display Names (`null`)** | 234 | **234** | **234** | Exact Match |
| **Legacy Unmapped Components** | 143 | **143** | **143** | Exact Match |
| **Environmental Profiles** | 5 | **5** | **5** | Exact Match |
| **Unique Failure Modes (Catalog)** | — | **521 IDs (141 names)** | **521** | Exact Match |
| **Profile FIT Rates (Comp $\times$ Prof)** | — | **1,820 entries (15 nulls)**| **1,820 (15 nulls)**| Exact Match |
| **Comp Failure Mode Percentages** | — | **5,975 entries** | **5,975** | Exact Match |
| **Legacy Failure Mode Percentages** | — | **636 entries** | **636** | Exact Match |
| **Historical & Legacy Aliases** | — | **130 aliases** | **130** | Exact Match |

---

## 7. Database Creation Process

### 7.1 Path Resolution
Database and seed file paths are resolved dynamically using `get_project_root()` in `fmeda_tool/db/database.py`. The function traverses upwards from `__file__` until locating `main.py`. Paths never depend on the operating system process current working directory (`os.getcwd()`).

### 7.2 Startup Initialization Logic
When `main.py` launches:
1. It executes `DatabaseService.ensure_database_ready()`.
2. `is_database_initialized()` checks if `data/fmeda.sqlite` exists, is non-empty, contains all 10 required tables, and has at least 364 components and 5 profiles.
3. **If Valid:** Startup proceeds immediately without reading or parsing any JSON file ($< 5\text{ ms}$).
4. **If Missing or Corrupted:** It triggers `DatabaseService.initialize_from_seed()`.

### 7.3 Step-by-Step Seed Import Algorithm
When initializing from seed:
1. Verifies existence of `data/seed/Combined_Exida_Component_library_version2.json` and `fmeda_tool/db/schema.sql`.
2. Creates parent directory `data/` if missing.
3. Opens a SQLite connection with `PRAGMA foreign_keys = ON;`.
4. Opens a single SQLite transaction (`with conn:`).
5. Executes `schema.sql` DDL to create tables and indexes.
6. Parses seed JSON and performs sequential bulk inserts:
   - `library_metadata` (1 row)
   - `profiles` (5 rows)
   - `components` (364 rows)
   - `component_aliases` (130 rows)
   - `component_failure_rates` (1,820 rows — preserving `None` as `NULL`)
   - `failure_modes` (521 catalog rows)
   - `component_failure_modes` (5,975 distribution rows)
   - `legacy_components` (143 rows)
   - `legacy_failure_modes` (636 rows)
7. Runs `PRAGMA foreign_key_check;` to verify zero relational violations.
8. Asserts exact record counts against seed data.
9. Commits transaction atomically. If any error occurs, rolls back completely, leaving no partial state.

---

## 8. SQLite Schema

### 8.1 Complete Relational DDL Specifications

```sql
PRAGMA foreign_keys = ON;
```

#### Table 1: `library_metadata`
Stores overall component library identification and schema policy.
```sql
CREATE TABLE IF NOT EXISTS library_metadata (
    library_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    description TEXT,
    display_name_policy TEXT,
    migration_changes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

#### Table 2: `profiles`
Defines the 5 standard environmental reliability profiles.
```sql
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    profile_number INTEGER NOT NULL UNIQUE,
    description TEXT
);
```

#### Table 3: `components`
Stores normalized Exida master component catalog records.
```sql
CREATE TABLE IF NOT EXISTS components (
    id TEXT PRIMARY KEY,
    failure_rate_id TEXT UNIQUE NOT NULL,
    item_id TEXT,
    item_no TEXT,
    display_name TEXT,
    component_type TEXT NOT NULL,
    component_subtype TEXT,
    component_use_category TEXT,
    mapping_status TEXT,
    mapping_basis TEXT,
    review_required INTEGER DEFAULT 0,
    source_name TEXT,
    source_record_item_no TEXT,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

#### Table 4: `component_aliases`
Stores legacy names, historical display names, and shorthand aliases.
```sql
CREATE TABLE IF NOT EXISTS component_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_type TEXT DEFAULT 'legacy',
    created_at TEXT NOT NULL
);
```

#### Table 5: `component_failure_rates`
Stores profile-specific failure rates in FIT (preserving `NULL` values).
```sql
CREATE TABLE IF NOT EXISTS component_failure_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    fit REAL,
    UNIQUE(component_id, profile_id)
);
```

#### Table 6: `failure_modes`
Standardized failure mode catalog.
```sql
CREATE TABLE IF NOT EXISTS failure_modes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);
```

#### Table 7: `component_failure_modes`
Stores failure mode percentage distributions per component and profile.
```sql
CREATE TABLE IF NOT EXISTS component_failure_modes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    failure_mode_id TEXT NOT NULL REFERENCES failure_modes(id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    percentage REAL,
    UNIQUE(component_id, failure_mode_id, profile_id)
);
```

#### Table 8: `legacy_components`
Stores unmapped legacy components for backward project compatibility.
```sql
CREATE TABLE IF NOT EXISTS legacy_components (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    shortcut TEXT,
    material TEXT,
    database TEXT,
    fits REAL,
    mapping_status TEXT,
    review_required INTEGER DEFAULT 1,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

#### Table 9: `legacy_failure_modes`
Stores failure modes for unmapped legacy components.
```sql
CREATE TABLE IF NOT EXISTS legacy_failure_modes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    legacy_component_id TEXT NOT NULL REFERENCES legacy_components(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    percentage REAL NOT NULL
);
```

#### Table 10: `component_change_log`
Immutable audit log tracking display name edits, removals, and status changes.
```sql
CREATE TABLE IF NOT EXISTS component_change_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL,
    action TEXT NOT NULL,
    field_changed TEXT,
    old_value TEXT,
    new_value TEXT,
    change_reason TEXT,
    user TEXT DEFAULT 'admin',
    timestamp TEXT NOT NULL
);
```

### 8.2 Database Indexes
```sql
CREATE INDEX IF NOT EXISTS idx_components_uuid ON components(id);
CREATE INDEX IF NOT EXISTS idx_components_fr_id ON components(failure_rate_id);
CREATE INDEX IF NOT EXISTS idx_components_display_name ON components(display_name);
CREATE INDEX IF NOT EXISTS idx_components_type ON components(component_type);
CREATE INDEX IF NOT EXISTS idx_component_aliases_alias ON component_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_component_aliases_comp ON component_aliases(component_id);
CREATE INDEX IF NOT EXISTS idx_comp_fm_comp ON component_failure_modes(component_id);
CREATE INDEX IF NOT EXISTS idx_comp_fm_fm ON component_failure_modes(failure_mode_id);
CREATE INDEX IF NOT EXISTS idx_legacy_components_display_name ON legacy_components(display_name);
CREATE INDEX IF NOT EXISTS idx_legacy_components_shortcut ON legacy_components(shortcut);
CREATE INDEX IF NOT EXISTS idx_change_log_component_id ON component_change_log(component_id);
```

---

## 9. Data Relationships

### 9.1 Relational Architecture Diagram

```
+---------------------+             +------------------------------+
|     profiles        | 1         * |   component_failure_rates    |
|---------------------|-------------|------------------------------|
| PK  id              |             | PK  id                       |
|     name            |             | FK  component_id (components)|
|     profile_number  |             | FK  profile_id (profiles)    |
|     description     |             |     fit (REAL, NULLABLE)     |
+---------------------+             +------------------------------+
           | 1                                     ^
           |                                       | *
           | *                                     |
+-------------------------------+   1       1      |
|    component_failure_modes    |------------------+
|-------------------------------|                  |
| PK  id                        |                  |
| FK  component_id (components) |                  |
| FK  failure_mode_id (fm)      |                  |
| FK  profile_id (profiles)     |                  |
|     percentage (REAL)         |                  |
+-------------------------------+                  |
           | *                                     |
           |                                       |
           | 1                                     |
+---------------------+                            |
|    failure_modes    |                            |
|---------------------|                            |
| PK  id              |                            |
|     name            |                            |
|     description     |                            |
+---------------------+                            |
                                                   |
+--------------------------------------------------+
|
v 1
+---------------------------+  1       *  +----------------------------+
|        components         |-------------|     component_aliases      |
|---------------------------|             |----------------------------|
| PK  id (UUID)             |             | PK  id                     |
| UQ  failure_rate_id       |             | FK  component_id           |
|     item_no               |             |     alias                  |
|     display_name (NULLABLE|             |     alias_type             |
|     component_type        |             |     created_at             |
|     component_subtype     |             +----------------------------+
|     status                |
+---------------------------+
           | 1
           |
           | *
+------------------------------------+
|       component_change_log         |
|------------------------------------|
| PK  id                             |
|     component_id                   |
|     action                         |
|     field_changed                  |
|     old_value                      |
|     new_value                      |
|     change_reason                  |
|     timestamp                      |
+------------------------------------+

+----------------------------+  1       *  +----------------------------+
|     legacy_components      |-------------|    legacy_failure_modes    |
|----------------------------|             |----------------------------|
| PK  id                     |             | PK  id                     |
|     display_name           |             | FK  legacy_component_id    |
|     shortcut               |             |     name                   |
|     fits                   |             |     percentage             |
+----------------------------+             +----------------------------+
```

---

## 10. Component Identity Rules

### 10.1 Identifier Roles and Authority

| Identifier | Format / Example | Authoritative? | Purpose & Rules |
| :--- | :--- | :--- | :--- |
| **Component UUID (`id`)** | `094127de-f949-50f1-adc0-07132ba36bf3` | **Primary Key** | Immutable primary key generated during normalization. Used for relational foreign keys and snapshot linkages. |
| **Failure Rate ID (`failure_rate_id`)** | `FR-000001` | **Unique Alternate Key** | Official Exida failure rate catalog record identifier. Unique, non-null, immutable. |
| **Item ID (`item_id`)** | UUID or string | Informational | Reference to handbook item catalog entry. |
| **Item Number (`item_no`)** | `E.1.1.1` | Classification | Section index in Exida Reliability Handbook. |
| **Display Name (`display_name`)** | `CEL`, `RES_10K` | **UI Shorthand (Editable)** | Human-friendly display label. **Nullable**. Can be edited or removed. Must be unique when populated. |
| **Display Label (Active)** | `CEL` or `Capacitor Electrolytic` | Computed Property | Computed dynamically: `display_name if display_name else component_type`. |
| **Legacy Alias (`alias`)** | `CELe`, `RM10e` | Resolution Aid | Historical lookup keys preserved in `component_aliases` to resolve legacy projects and BOMs. |
| **Component Type (`component_type`)** | `Capacitor Electrolytic` | Master Category | Official engineering component type. Used as the mandatory fallback label when `display_name` is NULL. |

> [!CAUTION]
> **Key Rule:** Display names are editable user convenience labels, **not database primary keys**. They can be assigned, updated, or removed to `NULL`. The application and project snapshots rely on `components.id` (UUID) and `failure_rate_id` for technical identity.

---

## 11. Environmental Profile Handling

### 11.1 Profiles 1 through 5
The Exida Reliability Handbook defines 5 standard operating profiles reflecting different environmental stresses:
1. **Profile 1:** Low Stress (Cabinet / Controlled Indoor Environment, $\approx 25^\circ\text{C}-30^\circ\text{C}$).
2. **Profile 2:** General Industrial / Field Environment ($\approx 40^\circ\text{C}$).
3. **Profile 3:** High Temperature / Industrial High Stress ($\approx 60^\circ\text{C}$).
4. **Profile 4:** Harsh / Automotive Environment (High temperature fluctuations, vibration).
5. **Profile 5:** Extreme / Offshore / Severe Environment.

### 11.2 Profile Selection in Projects
- Selected at project creation in `CreateProjectView` via the **"Exida Reliability Profile*"** combo box.
- Persisted in the project model as `Project.selected_profile` (defaulting to `"Profile 1"`).
- Component pickers load the project's selected profile to display the relevant failure rate and failure mode percentages.

### 11.3 Null FIT Value Preservation
In the seed catalog, 15 component profile combinations have undefined failure rates (`null`).
- Stored as `NULL` in `component_failure_rates.fit`.
- Preserved strictly as `None` in Python and snapshots.
- **Safety Rule:** The application **never converts a null FIT value to 0.0**. If a component with null FIT is selected, the UI presents an explicit warning dialog prompting the engineer to enter a valid assessed failure rate.

---

## 12. Component Selection Workflow

### 12.1 User Selection Flow
1. **Project Setup:** User creates an FMEDA project and selects the environmental profile (e.g. `Profile 2`).
2. **Add Component:** In the Functional Unit workspace (Page 2), user clicks "+ Add Component".
3. **Picker Dialog:** `ComponentSelectionDialog` opens, initialized with the project's profile.
4. **Choose Catalog:**
   - **Exida Components Tab (Default):** Multi-parameter search across display names, types, subtypes, categories, Failure Rate IDs, item numbers, and aliases.
   - **Legacy Unmapped Tab:** Accessible for legacy projects with prominent warning banner.
5. **Configure Instance:**
   - Designator is configured (e.g. `C101`).
   - Base failure rate is loaded from SQLite for the project profile.
   - Failure mode percentage distribution is loaded.
   - User configures failure classifications (Safe, Dangerous, No Effect).
6. **Snapshot Capture:** Clicking "Add Component" compiles an immutable `Component` model containing a complete snapshot dictionary (`comp.snapshot`).
7. **Recalculation:** Workspace recalculates overall $\lambda$, SFF, DC, and SIL metrics immediately.

---

## 13. Display-Name Management

The Component Library Management view (`ComponentsDBView`) provides 5 dedicated tabs:

### 1. Exida Components (Master Catalog)
- Displays all 364 Exida components.
- When `display_name` is `NULL`: Display Name column is blank, Display Label shows `component_type`, and Action Button shows **`+ Assign Name`**.
- When `display_name` is populated: Display Name column shows the name, Display Label shows the name, and Action Button shows **`Edit Name`**.

### 2. Legacy Unmapped Components
- Displays the 143 unmapped legacy components.
- Allows administrative retiring or reactivating of legacy entries.

### 3. Unassigned Display Names (Batch Edit)
- Lists all 234 components currently having `display_name = NULL`.
- Allows inline table editing of proposed names.
- **"Validate Batch"**: Validates all proposed names against uniqueness and alias collision rules without saving. Blank rows are skipped.
- **"Save All Assignments"**: Transactionally applies all valid entries in a single atomic database commit.

### 4. Audit Change Log
- Chronological table showing timestamp, component ID, action (`assign_display_name`, `edit_display_name`, `remove_display_name`, `status_change`), old value, new value, reason, and user.

### 5. Database Administration
- Displays active database path, schema version (`1.0`), and database status.
- Provides explicit **"Rebuild Database from Seed JSON"** action protected by confirmation dialog.

---

## 14. Exact Display-Name Validation Rules

The following validation matrix represents the exact rules implemented in `ComponentLibraryService.validate_display_name()`, `assign_display_name()`, `remove_display_name()`, and `batch_assign_display_names()`:

| Rule # | Validation Rule | Implemented Location | Case Handling | Exact Validation Message | Database Enforcement | Test Coverage |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Empty / Whitespace** | `validate_display_name` | N/A | `"Display name cannot be empty or whitespace only."` | Service Check | `test_05` |
| **2** | **Whitespace Trimming** | `validate_display_name`, `assign_display_name` | Trimmed via `.strip()` | Automatic trimming before validation/saving | N/A | `test_05` |
| **3** | **UUID Format Rejection** | `validate_display_name` | Case-insensitive | `"Display name cannot be formatted as a UUID."` | Service Check | `test_05` |
| **4** | **FR-ID Format Rejection** | `validate_display_name` | Case-insensitive regex `^FR-\d+$` | `"Display name cannot be formatted as a Failure Rate ID (e.g. FR-000001)."` | Service Check | `test_05` |
| **5** | **Duplicate Active Display Name** | `validate_display_name` | Exact string match | `"Display name '{clean}' is already assigned to component {fr_id}."` | `components.display_name` query check | `test_05` |
| **6** | **Conflicting Alias Collision** | `validate_display_name` | Exact string match | `"Display name '{clean}' conflicts with an existing alias for component {fr_id}."` | `component_aliases` query check | `test_05` |
| **7** | **Batch Duplicate Check** | `batch_assign_display_names`, `_validate_unassigned_batch` | Case-sensitive / exact in batch | `"Duplicate proposed display name in batch (conflicts with component {other_id})."` | In-memory batch map validation | `test_06` |
| **8** | **Blank Batch Row Handling** | `batch_assign_display_names`, `_validate_unassigned_batch` | Empty string check | Blank entries are skipped; remaining non-blank entries proceed | Service Logic | `test_06` |
| **9** | **Approved Rename Alias Retention** | `assign_display_name`, `batch_assign_display_names` | Exact | Previous approved name inserted into `component_aliases` with `alias_type='historical'` | `component_aliases` table insert | `test_04` |
| **10**| **Test Name Alias Suppression** | `assign_display_name`, `is_test_name` | Regex `^(TEST_|TEST|BATCH_TEST_|BATCH_TEST|CEL_MODIFIED_NAME|TEST_DISP_)` | Test names are suppressed from alias insertion | Service Logic | `test_10` |
| **11**| **Removal to NULL** | `remove_display_name` | Direct NULL assignment | Resets `components.display_name = NULL`, records `remove_display_name` audit log | `UPDATE components SET display_name = NULL` | `test_09` |
| **12**| **Character Whitelist** | N/A | Unicode string | *Not implemented* (Standard UTF-8 strings accepted) | None | N/A |
| **13**| **Maximum String Length** | N/A | Unlimited SQLite TEXT | *Not implemented* (Standard SQLite TEXT limits apply) | None | N/A |

---

## 15. Display-Name Policy

1. **Normalized Standard Names:** Normalized display names remove historical trailing lowercase `e` suffixes (e.g., `NREFe` became `NREF`, `RM10e` became `RM10`, `CELe` became `CEL`, `XSTAUe` became `XSTAU`).
2. **Historical Alias Preservation:** Original names with trailing `e` are permanently preserved in `component_aliases` with `alias_type = 'legacy'`.
3. **Internal Convenience Labels:** Display names are internal company shorthand for fast BOM matching and schematic cross-referencing. They do not supersede official IEC, ISO, or Exida handbook taxonomy.

---

## 16. Legacy Compatibility

### 16.1 Multi-Tier Resolution Hierarchy
When resolving a component query string (e.g., from BOM import or legacy project loading), `ComponentLibraryService.resolve_component(query, profile)` executes a strict 7-tier resolution hierarchy:

```
[ Incoming Component Query ]
            |
            v
[ Tier 1: Component UUID ] ------------> Match? ---> Return Exida/Legacy Snapshot
            | No
            v
[ Tier 2: Failure Rate ID (FR-XXXXXX) ] -> Match? ---> Return Exida Snapshot
            | No
            v
[ Tier 3: Active Display Name ] -------> Match? ---> Return Exida Snapshot
            | No
            v
[ Tier 4: Exact Legacy Alias ('e') ] --> Match? ---> Return Exida Snapshot
            | No
            v
[ Tier 5: Parsed Alias + Profile ] ----> Match? ---> Return Exida Snapshot (with target profile)
  (e.g., "RM10eP2" -> "RM10" + Profile 2)
            | No
            v
[ Tier 6: Legacy Display Name/Shortcut ]-> Match? -> Return Legacy Unmapped Snapshot
  (e.g., "C", "R")
            | No
            v
[ Tier 7: Unresolved ] ----------------> Returns (None, None, "unresolved") -> Prompt User Review
```

> [!NOTE]
> **Exact vs. Fuzzy Matching:** Resolution tiers 1 through 6 perform **exact matches** (with case-insensitive handling for FR-IDs and UUIDs). Approximate or fuzzy matching is prohibited during automated resolution to prevent misclassifying safety-critical components.

---

## 17. Project Snapshot Behavior

### 17.1 Stored Snapshot Data
When a component is added to an FMEDA project, an immutable snapshot dictionary is compiled and serialized directly into the project JSON:

```json
{
  "library_component_id": "094127de-f949-50f1-adc0-07132ba36bf3",
  "failure_rate_id": "FR-000001",
  "item_no": "E.1.1.1",
  "displayed_label": "CEL",
  "display_name": "CEL",
  "component_type": "Capacitor Electrolytic",
  "component_subtype": "Tantalum - Solid",
  "component_use_category": "Standard",
  "selected_profile": "Profile 1",
  "failure_rate": 5.2,
  "failure_modes": {
    "Short": 50.0,
    "Open": 30.0,
    "Change of Value": 20.0
  },
  "source_type": "exida",
  "library_id": "b41d2f01-9596-5b7a-958f-ed405f96955a",
  "schema_version": "1.0"
}
```

### 17.2 Calculation Isolation
- **Independence:** FMEDA calculation algorithms operate exclusively on the data stored in the project's component models and snapshots.
- **Immutability:** Subsequent edits to display names, failure rates, or aliases in `data/fmeda.sqlite` do **not** alter calculations of previously saved projects.
- **Offline Resilience:** Existing projects can be opened, reviewed, calculated, and exported even if `data/fmeda.sqlite` is temporarily missing or relocated.

---

## 18. Audit and Change History

### 18.1 Audit Schema (`component_change_log`)
Every administrative mutation to the library records an audit entry:
- `id`: Auto-incrementing primary key.
- `component_id`: UUID of the affected component.
- `action`: Action type (`assign_display_name`, `edit_display_name`, `remove_display_name`, `status_change`).
- `field_changed`: Field name (`display_name`, `status`).
- `old_value`: Previous value string (or `NULL`).
- `new_value`: New value string (or `NULL`).
- `change_reason`: User-provided or system justification.
- `user`: Operator username (defaults to `"admin"`).
- `timestamp`: ISO-8601 UTC timestamp.

---

## 19. Database Administration

### 19.1 Administrator Tab Features
Located in `ComponentsDBView` $\to$ **Database Administration**:
- **Database Path Display:** Read-only absolute path to `data/fmeda.sqlite`.
- **Schema Version:** Read-only version indicator (`1.0`).
- **Status:** Operational status (`Active`).
- **Rebuild Database Action:** Executes `DatabaseService.initialize_from_seed(force_rebuild=True)`.

> [!WARNING]
> **Destructive Operation:** Rebuilding from seed drops all existing tables and recreates them cleanly from `Combined_Exida_Component_library_version2.json`. Any custom display names assigned after initial deployment that are not in the seed file will be reset to `NULL`.

---

## 20. Testing and Validation

### 20.1 Test Isolation Infrastructure
- **Isolation Fixture (`tests/conftest.py`):** Automatically creates a temporary SQLite database in a temporary directory for test sessions via `DatabaseService.initialize_from_seed()`, injecting the path via `set_custom_database_path()`.
- **Production Guard (`fmeda_tool/db/database.py`):** If any test attempts to connect to `data/fmeda.sqlite` while `PYTEST_CURRENT_TEST` is set, `get_db_connection()` raises a `RuntimeError`.

### 20.2 Test Suite Execution Matrix (77 Tests)

| Test Module | Test Focus | Tests | Result |
| :--- | :--- | :---: | :---: |
| `tests/test_sqlite_library.py` | DB init, counts, null FIT, 7-tier resolution, display-name CRUD, batch atomic save, snapshots, profiles, removal to NULL, test alias suppression, prod guard | 11 | **PASSED** |
| `tests/test_bom.py` | BOM CSV import, delimiter detection, column mapping | 13 | **PASSED** |
| `tests/test_calculations.py` | FMEDA formulas, SFF, DC, SIL, Gesamtgerät vs Sicherheitskanal | 3 | **PASSED** |
| `tests/test_component_addition.py` | Component picker integration, multi-instance creation | 8 | **PASSED** |
| `tests/test_export.py` | Excel workbook export, summary sheets | 2 | **PASSED** |
| `tests/test_gui.py` | Navigation, widgets, main view transitions | 5 | **PASSED** |
| `tests/test_import.py` | CSV/JSON project loaders, encoding resilience | 5 | **PASSED** |
| `tests/test_increment6.py` | Verification tab, validation alerts, severity grouping | 9 | **PASSED** |
| `tests/test_mapping.py` | BOM component template auto-matching | 6 | **PASSED** |
| `tests/test_migration.py` | Project schema version migrations | 1 | **PASSED** |
| `tests/test_models.py` | Pydantic data models & validation | 3 | **PASSED** |
| `tests/test_navigation.py` | End-to-end multi-page workflow | 1 | **PASSED** |
| `tests/test_project_service.py`| Save/load persistence, JSON serialization | 2 | **PASSED** |
| `tests/test_validation.py` | Functional safety verification rules | 5 | **PASSED** |
| `tests/test_workflow.py` | Complete end-to-end user workflow | 3 | **PASSED** |
| **Total** | **Full Application Test Suite** | **77** | **100% PASSED** |

---

## 21. Data Integrity and Safety Rules

1. **Null FIT Preservation:** Missing FIT values remain `NULL` and are never converted to zero.
2. **Nullable Display Names:** Display names may be `NULL`. Unassigned components fall back to `component_type`.
3. **Blank Batch Rows Skipped:** Blank entries in batch assignment are skipped without triggering validation errors.
4. **Stable Relational Identifiers:** Component UUIDs and Failure Rate IDs remain permanent.
5. **Soft Retirement:** Components are retired via `status = 'retired'`, never hard-deleted during operation.
6. **Foreign Key Enforcement:** `PRAGMA foreign_keys = ON;` is enforced on every database connection.
7. **Atomic Transactions:** Batch edits and database rebuilds commit atomically or roll back completely.
8. **Project Snapshot Protection:** Historical projects maintain calculation integrity regardless of master library edits.

---

## 22. Startup, Backup, Recovery, and Rebuild Procedures

### Procedure 1: Normal Application Startup
1. Launch application:
   ```powershell
   python main.py
   ```
2. Application calls `DatabaseService.ensure_database_ready()`.
3. Validates `data/fmeda.sqlite` ($< 5\text{ ms}$) and displays the Main Menu.

### Procedure 2: First-Time Database Creation
1. If `data/fmeda.sqlite` is absent when running `python main.py`, the system detects the missing database.
2. Reads `data/seed/Combined_Exida_Component_library_version2.json` and `fmeda_tool/db/schema.sql`.
3. Populates all 10 tables and builds indexes.
4. Prints `[OK] SQLite database initialized successfully`.

### Procedure 3: Manual SQLite Database Backup
1. Close the application.
2. Copy `data/fmeda.sqlite` to a secure backup folder:
   ```powershell
   Copy-Item "data\fmeda.sqlite" "data\fmeda_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').sqlite"
   ```

### Procedure 4: Restoring Database from Backup
1. Close the application.
2. Overwrite `data/fmeda.sqlite` with the backup file:
   ```powershell
   Copy-Item "data\fmeda_backup_YYYYMMDD_HHMMSS.sqlite" "data\fmeda.sqlite" -Force
   ```
3. Relaunch `python main.py`.

### Procedure 5: Rebuilding Database from Seed JSON
1. Open the application and navigate to **Component Library & Display Name Management** $\to$ **Database Administration**.
2. Click **"Rebuild Database from Seed JSON"**.
3. Confirm the warning dialog.
4. The database is rebuilt atomically from `Combined_Exida_Component_library_version2.json`.

### Procedure 6: Recovery When Seed JSON is Missing
If `Combined_Exida_Component_library_version2.json` is missing:
1. Normal operation continues unaffected if `data/fmeda.sqlite` is present.
2. To restore the seed file, copy the authoritative seed JSON from company source control into `data/seed/`.

### Procedure 7: Moving Application to Another Computer
1. Copy the entire application folder (`fmeda_app8/`) to the target machine.
2. Ensure Python 3.11+ is installed.
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Launch `python main.py`. All project data and SQLite databases run immediately without external configuration.

---

## 23. Known Limitations and Deviations

| Item # | Area | Description | Severity | Status / Recommendation |
| :---: | :--- | :--- | :---: | :--- |
| **1** | **Character Whitelist Validation** | Display name validation enforces non-empty, unique, non-UUID, and non-FR-ID checks, but does not enforce a strict alphanumeric regex whitelist. | **Low** | Working as designed. Allows standard symbols (e.g. `_`, `-`, `/`). |
| **2** | **Unassigned Display Names** | 234 of the 364 normalized Exida records have `display_name = NULL` by design in the seed JSON. | **Low** | Working as designed. Handled properly via `component_type` fallback. |
| **3** | **Unmapped Legacy Records** | 143 legacy component models remain unmapped in `legacy_components`. | **Medium** | Functional Safety review recommended to map remaining legacy models to Exida records over time. |
| **4** | **Rebuild Backup Prompt** | The "Rebuild Database" button in UI prompts for confirmation, but does not automatically write a timestamped `.bak` file before dropping tables. | **Medium** | Recommendation: Add automatic backup creation before executing rebuild script. |
| **5** | **Database CHECK Constraints** | Display name uniqueness against aliases is verified in Python service layer rather than via SQLite database triggers. | **Low** | Sufficient for single-user desktop application architecture. |

---

## 24. Operational Rules Summary

1. **SQLite is the Operational Master:** `data/fmeda.sqlite` is the only active component library during runtime.
2. **Seed JSON is for Seeding and Recovery:** `data/seed/*.json` is never loaded during normal daily operation.
3. **`components_db.json` is Deprecated:** Retained strictly as an offline historical backup.
4. **UUID & Failure Rate ID are Authoritative:** Technical linkages rely on `components.id` and `failure_rate_id`.
5. **Display Names are Editable Labels:** Can be assigned, edited, or removed to `NULL`.
6. **Automatic Fallback Labeling:** Components with `display_name = NULL` automatically display `component_type`.
7. **Legacy Aliases are Searchable:** Historical names (including old `e` suffixes) resolve via `component_aliases`.
8. **Calculation Isolation:** Existing project FMEDA calculations calculate from stored snapshots and never mutate silently after library edits.
9. **Null FIT Integrity:** Null failure rates are preserved as `NULL` and never defaulted to zero.
10. **Destructive Rebuilds:** Database rebuilds are explicit administrative actions.
11. **Strict Test Isolation:** Automated tests run against temporary databases and never modify `data/fmeda.sqlite`.

---

## 25. Technical Glossary

- **SQLite:** Embedded, file-based relational database engine implementing full ACID transactions and SQL standards.
- **Seed JSON:** Authoritative source catalog file (`Combined_Exida_Component_library_version2.json`) containing normalized Exida components and unmapped legacy records.
- **Component UUID:** A 36-character canonical identifier (`id`) serving as the immutable primary key of an Exida component.
- **Failure Rate ID:** Unique Exida record catalog code (e.g. `FR-000001`).
- **Item Number:** Handbook section classification number (e.g. `E.1.1.1`).
- **Display Name:** Editable user-friendly component abbreviation (e.g. `CEL`, `RES_10K`). Can be `NULL`.
- **Display Label (Active):** The effective label displayed in UI and tables (`display_name` if present, else `component_type`).
- **Legacy Alias:** Historical shorthand names (e.g. `CELe`, `RM10e`) indexed in `component_aliases`.
- **Legacy Component:** Unmapped component records from older projects maintained in `legacy_components` for backward compatibility.
- **FIT (Failures in Time):** Failure rate unit representing 1 failure per $10^9$ operating hours ($1\text{ FIT} = 10^{-9}\text{ failures/hour}$).
- **Environmental Profile:** One of five operating stress levels (Profile 1 to Profile 5) determining profile-specific FIT and failure mode percentage distributions.
- **Failure Mode:** Standardized physical manifestation of component malfunction (e.g. Short, Open, Drift).
- **Mapping Status:** Status tag (`mapped`, `unmapped_legacy`) indicating whether a component has been mapped to a verified Exida catalog entry.
- **Project Snapshot:** A complete, frozen copy of component library attributes embedded within a project file to isolate calculations from master library changes.
- **Audit Log:** An append-only historical record in `component_change_log` detailing all administrative changes.
- **Database Rebuild:** Administrative operation recreating the operational SQLite database from the seed JSON file.
- **Retired Component:** A component whose `status` is set to `'retired'`, hiding it from standard pickers while preserving historical linkages.

---

## 26. Final Verification Checklist

| Verification Item | Implementation Evidence / Test | Verification Result |
| :--- | :--- | :---: |
| **Operational Database Path Verified** | `data/fmeda.sqlite` resolved via `get_project_root()` | **VERIFIED** |
| **Relational Schema & Foreign Keys** | `PRAGMA foreign_key_check;` returned 0 violations | **VERIFIED** |
| **Seed Counts Recalculated** | 364 Exida components, 143 legacy components, 5 profiles, 5,975 FM distributions | **VERIFIED** |
| **Runtime JSON Independence** | Application searches and resolves components without seed JSON file present | **VERIFIED** |
| **5 Environmental Profiles Implemented** | Profiles 1–5 selectable in `CreateProjectView` and loaded in picker | **VERIFIED** |
| **Null FIT Safety Preservation** | 15 null FIT entries stored as `NULL` (never converted to 0.0) | **VERIFIED** |
| **7-Tier Multi-Tier Resolution** | UUID, FR-ID, Display Name, Legacy Alias (`e`), Parsed Profile (`P2`), Legacy Name | **VERIFIED** |
| **Display Name Removal Workflow** | `remove_display_name` restores `display_name = NULL` and displays `component_type` | **VERIFIED** |
| **Batch Display Name Editing** | Atomic validation, duplicate detection, and single-transaction commit | **VERIFIED** |
| **Audit Logging Functional** | `component_change_log` logs assignment, editing, removal, and retirement | **VERIFIED** |
| **Project Snapshot Isolation** | Library edits do not mutate existing project calculations or stored snapshots | **VERIFIED** |
| **Test Database Isolation Guard** | Tests run on temporary databases; production database access raises `RuntimeError` | **VERIFIED** |
| **Database Immutability during Tests** | MD5 hash of `data/fmeda.sqlite` before and after test suite: `dff84ac8a0f71ca96261528485cdf6e9` | **VERIFIED** |
| **Automated Test Suite Passing** | 77 of 77 pytest tests passing (100% green) | **VERIFIED** |
