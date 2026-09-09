-- FMEDA Component Library SQLite Schema
PRAGMA foreign_keys = ON;

-- 1. Library Metadata
CREATE TABLE IF NOT EXISTS library_metadata (
    library_id TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL,
    description TEXT,
    display_name_policy TEXT,
    migration_changes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- 2. Profiles (Profile 1 to 5)
CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    profile_number INTEGER NOT NULL UNIQUE,
    description TEXT
);

-- 3. Normalized Exida Components
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

-- 4. Component Aliases (Historical & Legacy names)
CREATE TABLE IF NOT EXISTS component_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    alias_type TEXT DEFAULT 'legacy',
    created_at TEXT NOT NULL
);

-- 5. Component Profile Failure Rates (FIT)
CREATE TABLE IF NOT EXISTS component_failure_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    fit REAL,
    UNIQUE(component_id, profile_id)
);

-- 6. Failure Modes (Catalog)
CREATE TABLE IF NOT EXISTS failure_modes (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT
);

-- 7. Component Failure Mode Percentages per Profile
CREATE TABLE IF NOT EXISTS component_failure_modes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component_id TEXT NOT NULL REFERENCES components(id) ON DELETE CASCADE,
    failure_mode_id TEXT NOT NULL REFERENCES failure_modes(id) ON DELETE CASCADE,
    profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    percentage REAL,
    UNIQUE(component_id, failure_mode_id, profile_id)
);

-- 8. Legacy Components (Unmapped)
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

-- 9. Legacy Failure Modes
CREATE TABLE IF NOT EXISTS legacy_failure_modes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    legacy_component_id TEXT NOT NULL REFERENCES legacy_components(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    percentage REAL NOT NULL
);

-- 10. Component Change Log (Audit Trail)
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

-- Indexes for fast resolution and queries
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
