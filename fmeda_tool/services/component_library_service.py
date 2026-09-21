"""
Component Library Service for normalized SQLite component operations,
multi-tier resolution, project snapshotting, and display-name management.
"""

import re
import uuid
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path

from fmeda_tool.db.database import get_db_connection, ensure_database_ready

logger = logging.getLogger(__name__)


class ComponentLibraryService:
    """Service providing query, resolution, and administrative management for the SQLite component library."""
    
    @staticmethod
    def is_test_name(name: Optional[str]) -> bool:
        """Checks whether a display name or alias matches test patterns."""
        if not name:
            return False
        clean = str(name).strip()
        pattern = r"^(TEST_|TEST|BATCH_TEST_|BATCH_TEST|CEL_MODIFIED_NAME|TEST_DISP_)"
        return bool(re.match(pattern, clean, re.IGNORECASE))
    
    @staticmethod
    def _normalize_profile_id(profile: Optional[str]) -> str:
        """Normalizes a profile name or number (e.g. 'Profile 1', 'P1', 1) to 'profile_1'."""
        if not profile:
            return "profile_1"
        prof_str = str(profile).strip()
        match = re.search(r"(\d+)", prof_str)
        if match:
            return f"profile_{match.group(1)}"
        return prof_str.lower().replace(" ", "_")

    @staticmethod
    def _profile_id_to_name(profile_id: str) -> str:
        """Converts profile_1 to 'Profile 1'."""
        match = re.search(r"(\d+)", profile_id)
        if match:
            return f"Profile {match.group(1)}"
        return profile_id.replace("_", " ").title()

    @staticmethod
    def get_profiles(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Returns all available profiles."""
        ensure_database_ready(db_path=db_path)
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            rows = cur.execute("SELECT id, name, profile_number, description FROM profiles ORDER BY profile_number").fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_distinct_filter_values(db_path: Optional[Path] = None) -> Dict[str, List[str]]:
        """Returns distinct values for dropdown filtering in component pickers."""
        ensure_database_ready(db_path=db_path)
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            exida_types = [r[0] for r in cur.execute("SELECT DISTINCT component_type FROM components WHERE component_type IS NOT NULL ORDER BY component_type").fetchall()]
            try:
                custom_types = [r[0] for r in cur.execute("SELECT DISTINCT component_type FROM custom_components WHERE component_type IS NOT NULL ORDER BY component_type").fetchall()]
            except Exception:
                custom_types = []
            all_types = sorted(list(set(exida_types + custom_types)))
            subtypes = [r[0] for r in cur.execute("SELECT DISTINCT component_subtype FROM components WHERE component_subtype IS NOT NULL AND component_subtype != '' ORDER BY component_subtype").fetchall()]
            categories = [r[0] for r in cur.execute("SELECT DISTINCT component_use_category FROM components WHERE component_use_category IS NOT NULL AND component_use_category != '' ORDER BY component_use_category").fetchall()]
            mapping_statuses = [r[0] for r in cur.execute("SELECT DISTINCT mapping_status FROM components WHERE mapping_status IS NOT NULL ORDER BY mapping_status").fetchall()]
            
            return {
                "component_types": all_types,
                "component_subtypes": subtypes,
                "component_use_categories": categories,
                "mapping_statuses": mapping_statuses
            }

    @staticmethod
    def search_exida_components(
        query: str = "",
        component_type: Optional[str] = None,
        component_subtype: Optional[str] = None,
        component_use_category: Optional[str] = None,
        mapping_status: Optional[str] = None,
        status: str = "active",
        profile: str = "Profile 1",
        include_retired: bool = False,
        db_path: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches Exida components table across display_name, legacy_aliases,
        component_type, component_subtype, component_use_category, failure_rate_id, item_no.
        """
        ensure_database_ready(db_path=db_path)
        profile_id = ComponentLibraryService._normalize_profile_id(profile)
        
        sql = """
            SELECT 
                c.id,
                c.failure_rate_id,
                c.item_id,
                c.item_no,
                c.display_name,
                c.component_type,
                c.component_subtype,
                c.component_use_category,
                c.mapping_status,
                c.mapping_basis,
                c.review_required,
                c.source_name,
                c.source_record_item_no,
                c.status,
                cfr.fit
            FROM components c
            LEFT JOIN component_failure_rates cfr 
                ON c.id = cfr.component_id AND cfr.profile_id = ?
            WHERE 1=1
        """
        params: List[Any] = [profile_id]
        
        if not include_retired and status:
            sql += " AND c.status = ?"
            params.append(status)
            
        if component_type and component_type != "All":
            sql += " AND c.component_type = ?"
            params.append(component_type)
            
        if component_subtype and component_subtype != "All":
            sql += " AND c.component_subtype = ?"
            params.append(component_subtype)
            
        if component_use_category and component_use_category != "All":
            sql += " AND c.component_use_category = ?"
            params.append(component_use_category)
            
        if mapping_status and mapping_status != "All":
            sql += " AND c.mapping_status = ?"
            params.append(mapping_status)
            
        sql += " ORDER BY c.failure_rate_id ASC"
        
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            rows = cur.execute(sql, params).fetchall()
            
            # Fetch aliases for all matching components in one query
            comp_ids = [r["id"] for r in rows]
            alias_map: Dict[str, List[str]] = {cid: [] for cid in comp_ids}
            if comp_ids:
                placeholders = ",".join("?" * len(comp_ids))
                alias_rows = cur.execute(
                    f"SELECT component_id, alias FROM component_aliases WHERE component_id IN ({placeholders})",
                    comp_ids
                ).fetchall()
                for a in alias_rows:
                    alias_map[a["component_id"]].append(a["alias"])
            
            # Fetch failure modes for Exida components
            fm_map: Dict[str, Dict[str, float]] = {cid: {} for cid in comp_ids}
            if comp_ids:
                placeholders = ",".join("?" * len(comp_ids))
                fm_rows = cur.execute(f"""
                    SELECT cfm.component_id, fm.name, cfm.percentage
                    FROM component_failure_modes cfm
                    JOIN failure_modes fm ON cfm.failure_mode_id = fm.id
                    WHERE cfm.component_id IN ({placeholders}) AND cfm.profile_id = ?
                    ORDER BY fm.name ASC
                """, (*comp_ids, profile_id)).fetchall()
                for fmr in fm_rows:
                    fm_map[fmr["component_id"]][fmr["name"]] = float(fmr["percentage"]) if fmr["percentage"] is not None else 0.0
            
            results = []
            q_lower = query.lower().strip()
            
            for r in rows:
                item = dict(r)
                cid = item["id"]
                aliases = alias_map.get(cid, [])
                item["aliases"] = aliases
                item["failure_modes"] = fm_map.get(cid, {})
                
                # Active label rule: display_name if available, else component_type
                item["display_label"] = item["display_name"] if item["display_name"] else item["component_type"]
                item["failure_rate"] = item.get("fit")
                
                # Filter query against fields
                if q_lower:
                    match = (
                        (item["display_name"] and q_lower in item["display_name"].lower()) or
                        (item["component_type"] and q_lower in item["component_type"].lower()) or
                        (item["component_subtype"] and q_lower in item["component_subtype"].lower()) or
                        (item["component_use_category"] and q_lower in item["component_use_category"].lower()) or
                        (item["failure_rate_id"] and q_lower in item["failure_rate_id"].lower()) or
                        (item["item_no"] and q_lower in str(item["item_no"]).lower()) or
                        any(q_lower in a.lower() for a in aliases) or
                        any(q_lower in k.lower() for k in item["failure_modes"].keys())
                    )
                    if not match:
                        continue
                        
                results.append(item)
                
            return results

    @staticmethod
    def get_exida_component_snapshot(
        component_id: str,
        profile: str = "Profile 1",
        db_path: Optional[Path] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Creates a complete standalone snapshot dictionary for an Exida component instance.
        """
        ensure_database_ready(db_path=db_path)
        profile_id = ComponentLibraryService._normalize_profile_id(profile)
        
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            comp = cur.execute("""
                SELECT 
                    c.id, c.failure_rate_id, c.item_id, c.item_no, c.display_name,
                    c.component_type, c.component_subtype, c.component_use_category,
                    c.mapping_status, c.mapping_basis, c.review_required,
                    c.source_name, c.source_record_item_no, c.status,
                    cfr.fit
                FROM components c
                LEFT JOIN component_failure_rates cfr 
                    ON c.id = cfr.component_id AND cfr.profile_id = ?
                WHERE c.id = ?
            """, (profile_id, component_id)).fetchone()
            
            if not comp:
                return None
                
            comp_dict = dict(comp)
            
            # Fetch aliases
            alias_rows = cur.execute("SELECT alias FROM component_aliases WHERE component_id = ?", (component_id,)).fetchall()
            aliases = [a[0] for a in alias_rows]
            
            # Fetch failure modes and profile-specific percentages
            fm_rows = cur.execute("""
                SELECT fm.name, cfm.percentage
                FROM component_failure_modes cfm
                JOIN failure_modes fm ON cfm.failure_mode_id = fm.id
                WHERE cfm.component_id = ? AND cfm.profile_id = ?
                ORDER BY fm.name
            """, (component_id, profile_id)).fetchall()
            
            failure_modes = {}
            for r in fm_rows:
                pct = r["percentage"]
                failure_modes[r["name"]] = float(pct) if pct is not None else 0.0
                
            # Metadata
            meta = cur.execute("SELECT library_id, schema_version FROM library_metadata LIMIT 1").fetchone()
            lib_id = meta["library_id"] if meta else "b41d2f01-9596-5b7a-958f-ed405f96955a"
            schema_ver = meta["schema_version"] if meta else "1.0"
            
            displayed_label = comp_dict["display_name"] if comp_dict["display_name"] else comp_dict["component_type"]
            
            return {
                "library_component_id": comp_dict["id"],
                "failure_rate_id": comp_dict["failure_rate_id"],
                "item_no": comp_dict["item_no"],
                "displayed_label": displayed_label,
                "display_name": comp_dict["display_name"],
                "component_type": comp_dict["component_type"],
                "component_subtype": comp_dict["component_subtype"],
                "component_use_category": comp_dict["component_use_category"],
                "selected_profile": ComponentLibraryService._profile_id_to_name(profile_id),
                "failure_rate": comp_dict["fit"],  # Can be None if null in DB
                "failure_modes": failure_modes,
                "source_type": "exida",
                "library_id": lib_id,
                "schema_version": schema_ver,
                "aliases": aliases
            }

    @staticmethod
    def search_legacy_components(
        query: str = "",
        status: str = "active",
        include_retired: bool = False,
        db_path: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """Searches legacy unmapped components."""
        ensure_database_ready(db_path=db_path)
        sql = """
            SELECT id, display_name, shortcut, material, database, fits, mapping_status, review_required, status
            FROM legacy_components
            WHERE 1=1
        """
        params: List[Any] = []
        if not include_retired and status:
            sql += " AND status = ?"
            params.append(status)
            
        sql += " ORDER BY display_name ASC"
        
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            rows = cur.execute(sql, params).fetchall()
            
            # Fetch failure modes for legacy components
            comp_ids = [r["id"] for r in rows]
            fm_map: Dict[str, Dict[str, float]] = {cid: {} for cid in comp_ids}
            if comp_ids:
                placeholders = ",".join("?" * len(comp_ids))
                fm_rows = cur.execute(
                    f"SELECT legacy_component_id, name, percentage FROM legacy_failure_modes WHERE legacy_component_id IN ({placeholders}) ORDER BY id ASC",
                    comp_ids
                ).fetchall()
                for fmr in fm_rows:
                    fm_map[fmr["legacy_component_id"]][fmr["name"]] = float(fmr["percentage"])
                    
            q_lower = query.lower().strip()
            results = []
            for r in rows:
                item = dict(r)
                cid = item["id"]
                item["failure_modes"] = fm_map.get(cid, {})
                item["failure_rate"] = item.get("fits")
                item["display_label"] = item.get("display_name")
                if q_lower:
                    match = (
                        (item["display_name"] and q_lower in item["display_name"].lower()) or
                        (item["shortcut"] and q_lower in item["shortcut"].lower()) or
                        (item["material"] and q_lower in item["material"].lower()) or
                        any(q_lower in k.lower() for k in item["failure_modes"].keys())
                    )
                    if not match:
                        continue
                results.append(item)
            return results

    @staticmethod
    def get_legacy_component_snapshot(
        component_id: str,
        db_path: Optional[Path] = None
    ) -> Optional[Dict[str, Any]]:
        """Creates snapshot dictionary for a legacy unmapped component."""
        ensure_database_ready(db_path=db_path)
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            comp = cur.execute("""
                SELECT id, display_name, shortcut, material, database, fits, mapping_status, review_required, status
                FROM legacy_components
                WHERE id = ?
            """, (component_id,)).fetchone()
            
            if not comp:
                return None
                
            comp_dict = dict(comp)
            
            fm_rows = cur.execute("""
                SELECT name, percentage FROM legacy_failure_modes WHERE legacy_component_id = ?
            """, (component_id,)).fetchall()
            
            failure_modes = {r["name"]: float(r["percentage"]) for r in fm_rows}
            
            return {
                "library_component_id": comp_dict["id"],
                "displayed_label": comp_dict["display_name"],
                "display_name": comp_dict["display_name"],
                "shortcut": comp_dict["shortcut"],
                "material": comp_dict["material"],
                "failure_rate": comp_dict["fits"],
                "failure_modes": failure_modes,
                "source_type": "legacy",
                "mapping_status": comp_dict["mapping_status"],
                "review_required": bool(comp_dict["review_required"])
            }

    @staticmethod
    def search_custom_components(
        query: str = "",
        component_type: Optional[str] = None,
        status: str = "active",
        include_retired: bool = False,
        db_path: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """Searches SQLite custom_components catalog."""
        ensure_database_ready(db_path=db_path)
        sql = """
            SELECT id, display_name, component_type, fits, status,
                   copied_from_source_type, copied_from_component_id,
                   copied_from_failure_rate_id, copied_at,
                   created_at, updated_at
            FROM custom_components
            WHERE 1=1
        """
        params: List[Any] = []
        if not include_retired and status:
            sql += " AND status = ?"
            params.append(status)
            
        if component_type and component_type != "All":
            sql += " AND component_type = ?"
            params.append(component_type)
            
        sql += " ORDER BY coalesce(display_name, component_type) ASC"
        
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            rows = cur.execute(sql, params).fetchall()
            
            # Fetch failure modes for all custom components
            comp_ids = [r["id"] for r in rows]
            fm_map: Dict[str, Dict[str, float]] = {cid: {} for cid in comp_ids}
            if comp_ids:
                placeholders = ",".join("?" * len(comp_ids))
                fm_rows = cur.execute(
                    f"SELECT custom_component_id, name, percentage FROM custom_failure_modes WHERE custom_component_id IN ({placeholders}) ORDER BY id ASC",
                    comp_ids
                ).fetchall()
                for fmr in fm_rows:
                    fm_map[fmr["custom_component_id"]][fmr["name"]] = float(fmr["percentage"])
                    
            q_lower = query.lower().strip()
            results = []
            for r in rows:
                item = dict(r)
                cid = item["id"]
                item["failure_modes"] = fm_map.get(cid, {})
                item["display_label"] = item["display_name"] if item["display_name"] else item["component_type"]
                
                if q_lower:
                    match = (
                        (item["display_name"] and q_lower in item["display_name"].lower()) or
                        (item["component_type"] and q_lower in item["component_type"].lower()) or
                        any(q_lower in k.lower() for k in item["failure_modes"].keys())
                    )
                    if not match:
                        continue
                results.append(item)
            return results

    @staticmethod
    def get_custom_component_snapshot(
        component_id: str,
        db_path: Optional[Path] = None
    ) -> Optional[Dict[str, Any]]:
        """Creates snapshot dictionary for a custom component."""
        ensure_database_ready(db_path=db_path)
        if isinstance(component_id, dict):
            component_id = component_id.get("library_component_id") or component_id.get("id")
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            comp = cur.execute("""
                SELECT id, display_name, component_type, fits, status,
                       copied_from_source_type, copied_from_component_id,
                       copied_from_failure_rate_id, copied_at,
                       created_at, updated_at
                FROM custom_components
                WHERE id = ?
            """, (component_id,)).fetchone()
            
            if not comp:
                return None
                
            comp_dict = dict(comp)
            fm_rows = cur.execute("""
                SELECT name, percentage FROM custom_failure_modes WHERE custom_component_id = ? ORDER BY id ASC
            """, (component_id,)).fetchall()
            
            failure_modes = {r["name"]: float(r["percentage"]) for r in fm_rows}
            displayed_label = comp_dict["display_name"] if comp_dict["display_name"] else comp_dict["component_type"]
            
            return {
                "library_component_id": comp_dict["id"],
                "displayed_label": displayed_label,
                "display_name": comp_dict["display_name"],
                "component_type": comp_dict["component_type"],
                "material": comp_dict["component_type"],
                "failure_rate": float(comp_dict["fits"]),
                "failure_modes": failure_modes,
                "source_type": "custom",
                "status": comp_dict["status"],
                "selected_profile": "Profile 1",
                "copied_from_source_type": comp_dict.get("copied_from_source_type"),
                "copied_from_component_id": comp_dict.get("copied_from_component_id"),
                "copied_from_failure_rate_id": comp_dict.get("copied_from_failure_rate_id"),
                "copied_at": comp_dict.get("copied_at"),
            }

    @staticmethod
    def create_custom_component(
        component_type: str,
        fits: float,
        failure_modes: Dict[str, float],
        display_name: Optional[str] = None,
        copied_from_source_type: Optional[str] = None,
        copied_from_component_id: Optional[str] = None,
        copied_from_failure_rate_id: Optional[str] = None,
        copied_at: Optional[str] = None,
        user: str = "admin",
        db_path: Optional[Path] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Creates and persists a new Custom Component in SQLite.
        Mandatory: component_type, fits, >= 2 failure modes.
        Optional: display_name (must be unique across all catalogs).
        Optional traceability: copied_from_source_type, copied_from_component_id, copied_from_failure_rate_id, copied_at.
        """
        if not component_type or not str(component_type).strip():
            return False, "Component Type is required.", None
            
        try:
            fit_val = float(fits)
            if fit_val < 0.0:
                return False, "FIT value must be non-negative.", None
        except (ValueError, TypeError):
            return False, "Valid FIT numeric value is required.", None
            
        if not failure_modes or len(failure_modes) < 2:
            return False, "At least 2 failure modes are required.", None
            
        for fm_name, fm_pct in failure_modes.items():
            if not fm_name or not str(fm_name).strip():
                return False, "Failure mode names cannot be empty.", None
            try:
                pct = float(fm_pct)
                if pct < 0.0:
                    return False, f"Failure mode percentage for '{fm_name}' must be non-negative.", None
            except (ValueError, TypeError):
                return False, f"Invalid percentage for failure mode '{fm_name}'.", None
                
        clean_dname = display_name.strip() if (display_name and display_name.strip()) else None
        if clean_dname:
            valid, msg = ComponentLibraryService.validate_display_name(clean_dname, db_path=db_path)
            if not valid:
                return False, msg, None
                
        c_id = f"custom_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now().isoformat()
        
        ensure_database_ready(db_path=db_path)
        conn = get_db_connection(db_path)
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO custom_components (
                        id, display_name, component_type, fits, status,
                        copied_from_source_type, copied_from_component_id,
                        copied_from_failure_rate_id, copied_at,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                """, (
                    c_id, clean_dname, component_type.strip(), fit_val,
                    copied_from_source_type, copied_from_component_id,
                    copied_from_failure_rate_id, copied_at or (now_str if copied_from_source_type else None),
                    now_str, now_str
                ))
                
                for fm_name, fm_pct in failure_modes.items():
                    cur.execute("""
                        INSERT INTO custom_failure_modes (custom_component_id, name, percentage)
                        VALUES (?, ?, ?)
                    """, (c_id, fm_name.strip(), float(fm_pct)))
                    
                disp_lbl = clean_dname or component_type.strip()
                action_desc = "Copied and created custom component" if copied_from_source_type else "Created custom component"
                cur.execute("""
                    INSERT INTO component_change_log (
                        component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                    ) VALUES (?, 'create_custom_component', 'all', NULL, ?, ?, ?, ?)
                """, (c_id, disp_lbl, action_desc, user, now_str))
                
            snap = ComponentLibraryService.get_custom_component_snapshot(c_id, db_path=db_path)
            return True, f"Custom component '{disp_lbl}' created successfully.", snap
        except Exception as e:
            conn.rollback()
            return False, f"Failed to create custom component: {e}", None
        finally:
            conn.close()

    @staticmethod
    def update_custom_component(
        custom_component_id: str,
        component_type: str,
        fits: float,
        failure_modes: Dict[str, float],
        display_name: Optional[str] = None,
        user: str = "admin",
        db_path: Optional[Path] = None
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Updates an existing Custom Component in SQLite."""
        if not component_type or not str(component_type).strip():
            return False, "Component Type is required.", None
            
        try:
            fit_val = float(fits)
            if fit_val < 0.0:
                return False, "FIT value must be non-negative.", None
        except (ValueError, TypeError):
            return False, "Valid FIT numeric value is required.", None
            
        if not failure_modes or len(failure_modes) < 2:
            return False, "At least 2 failure modes are required.", None
            
        for fm_name, fm_pct in failure_modes.items():
            if not fm_name or not str(fm_name).strip():
                return False, "Failure mode names cannot be empty.", None
            try:
                pct = float(fm_pct)
                if pct < 0.0:
                    return False, f"Failure mode percentage for '{fm_name}' must be non-negative.", None
            except (ValueError, TypeError):
                return False, f"Invalid percentage for failure mode '{fm_name}'.", None
                
        clean_dname = display_name.strip() if (display_name and display_name.strip()) else None
        if clean_dname:
            valid, msg = ComponentLibraryService.validate_display_name(clean_dname, current_component_id=custom_component_id, db_path=db_path)
            if not valid:
                return False, msg, None
                
        now_str = datetime.now().isoformat()
        ensure_database_ready(db_path=db_path)
        conn = get_db_connection(db_path)
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE custom_components
                    SET display_name = ?, component_type = ?, fits = ?, updated_at = ?
                    WHERE id = ?
                """, (clean_dname, component_type.strip(), fit_val, now_str, custom_component_id))
                
                cur.execute("DELETE FROM custom_failure_modes WHERE custom_component_id = ?", (custom_component_id,))
                
                for fm_name, fm_pct in failure_modes.items():
                    cur.execute("""
                        INSERT INTO custom_failure_modes (custom_component_id, name, percentage)
                        VALUES (?, ?, ?)
                    """, (custom_component_id, fm_name.strip(), float(fm_pct)))
                    
                disp_lbl = clean_dname or component_type.strip()
                cur.execute("""
                    INSERT INTO component_change_log (
                        component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                    ) VALUES (?, 'edit_custom_component', 'all', NULL, ?, 'Updated custom component', ?, ?)
                """, (custom_component_id, disp_lbl, user, now_str))
                
            snap = ComponentLibraryService.get_custom_component_snapshot(custom_component_id, db_path=db_path)
            return True, f"Custom component '{disp_lbl}' updated successfully.", snap
        except Exception as e:
            conn.rollback()
            return False, f"Failed to update custom component: {e}", None
        finally:
            conn.close()

    @staticmethod
    def delete_custom_component(
        custom_component_id: str,
        user: str = "admin",
        db_path: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """Deletes a custom component from SQLite."""
        ensure_database_ready(db_path=db_path)
        now_str = datetime.now().isoformat()
        conn = get_db_connection(db_path)
        try:
            with conn:
                cur = conn.cursor()
                comp = cur.execute("SELECT id, display_name, component_type FROM custom_components WHERE id = ?", (custom_component_id,)).fetchone()
                if not comp:
                    return False, f"Custom component '{custom_component_id}' not found."
                disp_lbl = comp["display_name"] or comp["component_type"]
                
                cur.execute("DELETE FROM custom_failure_modes WHERE custom_component_id = ?", (custom_component_id,))
                cur.execute("DELETE FROM custom_components WHERE id = ?", (custom_component_id,))
                
                cur.execute("""
                    INSERT INTO component_change_log (
                        component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                    ) VALUES (?, 'delete_custom_component', 'all', ?, NULL, 'Deleted custom component', ?, ?)
                """, (custom_component_id, disp_lbl, user, now_str))
            return True, f"Custom component '{disp_lbl}' deleted successfully."
        except Exception as e:
            conn.rollback()
            return False, f"Failed to delete custom component: {e}"
        finally:
            conn.close()

    @staticmethod
    def is_custom_component_referenced(
        custom_component_id: str,
        project: Optional[Any] = None,
        projects_dir: Optional[Path] = None,
        db_path: Optional[Path] = None
    ) -> Tuple[bool, str, List[Dict[str, str]]]:
        """
        Checks if a custom component is referenced in an active project or saved projects.
        Returns:
            (is_referenced, usage_summary_string, list_of_usage_dicts)
        """
        if not custom_component_id:
            return False, "No component ID provided.", []
            
        snap = ComponentLibraryService.get_custom_component_snapshot(custom_component_id, db_path=db_path)
        disp_name = snap.get("display_name") if snap else None
        disp_label = snap.get("displayed_label") if snap else None
        comp_type = snap.get("component_type") if snap else None
        
        candidates = {custom_component_id}
        if disp_name:
            candidates.add(disp_name.lower())
        if disp_label:
            candidates.add(disp_label.lower())
            
        references: List[Dict[str, str]] = []
        
        # 1. Check in-memory project
        if project is not None:
            p_name = getattr(project, "name", None) or getattr(project, "id", "Active Project")
            for unit in getattr(project, "units", []) or []:
                u_name = getattr(unit, "name", "Unit")
                # Check components
                for comp in getattr(unit, "components", []) or []:
                    lib_id = getattr(comp, "library_component_id", None)
                    c_id = getattr(comp, "id", None)
                    c_type = getattr(comp, "type", "") or ""
                    c_name = getattr(comp, "name", "") or ""
                    pos = getattr(comp, "position", "") or ""
                    src_type = getattr(comp, "source_type", "") or ""
                    
                    matched = False
                    if lib_id == custom_component_id or c_id == custom_component_id:
                        matched = True
                    elif src_type == "custom" and (c_type.lower() in candidates or c_name.lower() in candidates):
                        matched = True
                        
                    if matched:
                        references.append({
                            "project": p_name,
                            "unit": u_name,
                            "position": pos,
                            "component_name": c_name or c_type
                        })
                # Check component mappings / staged mappings
                comp_mappings = getattr(unit, "component_mappings", {}) or {}
                if isinstance(comp_mappings, dict):
                    for pos, m in comp_mappings.items():
                        m_lib_id = getattr(m, "library_component_id", None) if hasattr(m, "library_component_id") else (m.get("library_component_id") if isinstance(m, dict) else None)
                        m_id = getattr(m, "id", None) if hasattr(m, "id") else (m.get("id") if isinstance(m, dict) else None)
                        if m_lib_id == custom_component_id or m_id == custom_component_id:
                            references.append({
                                "project": p_name,
                                "unit": u_name,
                                "position": pos,
                                "component_name": "BOM Mapping"
                            })
                            
        # 2. Check saved projects on disk
        target_dir = projects_dir if projects_dir is not None else Path("data/projects")
        if target_dir.exists() and target_dir.is_dir():
            for p_file in target_dir.glob("*.json"):
                try:
                    with open(p_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        if custom_component_id in content or (disp_name and f'"{disp_name}"' in content):
                            import json
                            data = json.loads(content)
                            p_name = data.get("name", p_file.stem)
                            # Avoid duplicate logging if this is the active in-memory project
                            if project and getattr(project, "id", None) == data.get("id"):
                                continue
                            for u in data.get("units", []):
                                u_name = u.get("name", "Unit")
                                for c in u.get("components", []):
                                    if c.get("library_component_id") == custom_component_id or c.get("id") == custom_component_id or (c.get("source_type") == "custom" and (c.get("type", "").lower() in candidates or c.get("name", "").lower() in candidates)):
                                        references.append({
                                            "project": f"{p_name} (Saved Project)",
                                            "unit": u_name,
                                            "position": c.get("position", ""),
                                            "component_name": c.get("name", "") or c.get("type", "")
                                        })
                except Exception:
                    pass
                    
        if references:
            lines = ["This component is currently used and cannot be deleted.", "", "Usage details:"]
            for ref in references[:5]:
                pos_str = f" [Position: {ref['position']}]" if ref.get("position") else ""
                lines.append(f"• Project '{ref['project']}' -> Unit '{ref['unit']}'{pos_str} ({ref['component_name']})")
            if len(references) > 5:
                lines.append(f"• ... and {len(references) - 5} more references.")
            return True, "\n".join(lines), references
            
        return False, "Component is not referenced.", []


    @staticmethod
    def resolve_component(
        query: str,
        profile: str = "Profile 1",
        db_path: Optional[Path] = None
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], str]:
        """
        Multi-tier component resolution across Exida, Legacy, and Custom components.
        """
        if not query or not query.strip():
            return None, None, "empty_query"
            
        clean_q = query.strip()
        ensure_database_ready(db_path=db_path)
        
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            
            # Tier 1: Component UUID
            try:
                _ = uuid.UUID(clean_q)
                is_uuid = True
            except ValueError:
                is_uuid = False
                
            if is_uuid or clean_q.startswith("custom_"):
                row = cur.execute("SELECT id FROM components WHERE id = ?", (clean_q,)).fetchone()
                if row:
                    snap = ComponentLibraryService.get_exida_component_snapshot(row["id"], profile, db_path=db_path)
                    return "exida", snap, "uuid"
                    
                row_leg = cur.execute("SELECT id FROM legacy_components WHERE id = ?", (clean_q,)).fetchone()
                if row_leg:
                    snap = ComponentLibraryService.get_legacy_component_snapshot(row_leg["id"], db_path=db_path)
                    return "legacy", snap, "uuid"

                row_cust = cur.execute("SELECT id FROM custom_components WHERE id = ?", (clean_q,)).fetchone()
                if row_cust:
                    snap = ComponentLibraryService.get_custom_component_snapshot(row_cust["id"], db_path=db_path)
                    return "custom", snap, "uuid"
                    
            # Tier 2: Failure Rate ID
            if clean_q.upper().startswith("FR-"):
                row = cur.execute("SELECT id FROM components WHERE upper(failure_rate_id) = ?", (clean_q.upper(),)).fetchone()
                if row:
                    snap = ComponentLibraryService.get_exida_component_snapshot(row["id"], profile, db_path=db_path)
                    return "exida", snap, "failure_rate_id"
                    
            # Tier 3: Current display name
            row = cur.execute("SELECT id FROM components WHERE lower(display_name) = lower(?) AND status = 'active'", (clean_q,)).fetchone()
            if row:
                snap = ComponentLibraryService.get_exida_component_snapshot(row["id"], profile, db_path=db_path)
                return "exida", snap, "display_name"

            row_cust = cur.execute("SELECT id FROM custom_components WHERE lower(display_name) = lower(?) AND status = 'active'", (clean_q,)).fetchone()
            if row_cust:
                snap = ComponentLibraryService.get_custom_component_snapshot(row_cust["id"], db_path=db_path)
                return "custom", snap, "display_name"
                
            # Tier 4: Exact legacy alias
            alias_row = cur.execute("""
                SELECT c.id 
                FROM component_aliases a
                JOIN components c ON a.component_id = c.id
                WHERE a.alias = ? AND c.status = 'active'
            """, (clean_q,)).fetchone()
            if alias_row:
                snap = ComponentLibraryService.get_exida_component_snapshot(alias_row["id"], profile, db_path=db_path)
                return "exida", snap, "legacy_alias"
                
            # Tier 5: Parsed base alias + profile suffix
            match = re.match(r"^(.+?)[eE]?[pP](\d+)$", clean_q)
            if match:
                base_part = match.group(1)
                prof_num = match.group(2)
                target_profile = f"Profile {prof_num}"
                
                alias_patterns = [f"{base_part}e", base_part, f"{base_part}E"]
                for ap in alias_patterns:
                    ar = cur.execute("""
                        SELECT c.id 
                        FROM component_aliases a
                        JOIN components c ON a.component_id = c.id
                        WHERE a.alias = ? AND c.status = 'active'
                    """, (ap,)).fetchone()
                    if ar:
                        snap = ComponentLibraryService.get_exida_component_snapshot(ar["id"], target_profile, db_path=db_path)
                        return "exida", snap, "parsed_alias_with_profile"
                        
                dr = cur.execute("""
                    SELECT id FROM components WHERE (lower(display_name) = lower(?) OR lower(display_name) = lower(?)) AND status = 'active'
                """, (base_part, f"{base_part}e")).fetchone()
                if dr:
                    snap = ComponentLibraryService.get_exida_component_snapshot(dr["id"], target_profile, db_path=db_path)
                    return "exida", snap, "parsed_alias_with_profile"
                    
            # Tier 6: Exact unresolved legacy display name / shortcut
            leg_row = cur.execute("""
                SELECT id FROM legacy_components WHERE (lower(display_name) = lower(?) OR lower(shortcut) = lower(?)) AND status = 'active'
            """, (clean_q, clean_q)).fetchone()
            if leg_row:
                snap = ComponentLibraryService.get_legacy_component_snapshot(leg_row["id"], db_path=db_path)
                return "legacy", snap, "legacy_display_name"

            # Tier 7: Custom component by component_type
            cust_type_row = cur.execute("""
                SELECT id FROM custom_components WHERE lower(component_type) = lower(?) AND status = 'active'
            """, (clean_q,)).fetchone()
            if cust_type_row:
                snap = ComponentLibraryService.get_custom_component_snapshot(cust_type_row["id"], db_path=db_path)
                return "custom", snap, "custom_component_type"
                
            # Tier 8: Manual review / Unresolved
            return None, None, "unresolved"

    @staticmethod
    def validate_display_name(
        name: str,
        current_component_id: Optional[str] = None,
        db_path: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """
        Validates proposed display name across Exida, Legacy, and Custom components.
        If duplicate exists in any catalog, returns 'Display Name already exists.'
        """
        if not name or not name.strip():
            return False, "Display name cannot be empty or whitespace only."
            
        clean = name.strip()
        
        # Check UUID
        try:
            uuid.UUID(clean)
            return False, "Display name cannot be formatted as a UUID."
        except ValueError:
            pass
            
        # Check Failure Rate ID pattern
        if re.match(r"^FR-\d+$", clean, re.IGNORECASE):
            return False, "Display name cannot be formatted as a Failure Rate ID (e.g. FR-000001)."
            
        ensure_database_ready(db_path=db_path)
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            
            # 1. Check duplicate in Exida components
            if current_component_id:
                row = cur.execute(
                    "SELECT id FROM components WHERE lower(display_name) = lower(?) AND id != ?",
                    (clean, current_component_id)
                ).fetchone()
            else:
                row = cur.execute(
                    "SELECT id FROM components WHERE lower(display_name) = lower(?)",
                    (clean,)
                ).fetchone()
                
            if row:
                return False, "Display Name already exists. (already assigned to another component). Enter a unique name or leave it empty."
                
            # 2. Check duplicate in Legacy components
            if current_component_id:
                leg_row = cur.execute(
                    "SELECT id FROM legacy_components WHERE lower(display_name) = lower(?) AND id != ?",
                    (clean, current_component_id)
                ).fetchone()
            else:
                leg_row = cur.execute(
                    "SELECT id FROM legacy_components WHERE lower(display_name) = lower(?)",
                    (clean,)
                ).fetchone()
            if leg_row:
                return False, "Display Name already exists. (already assigned to another component). Enter a unique name or leave it empty."

            # 3. Check duplicate in Custom components
            if current_component_id:
                cust_row = cur.execute(
                    "SELECT id FROM custom_components WHERE lower(display_name) = lower(?) AND id != ?",
                    (clean, current_component_id)
                ).fetchone()
            else:
                cust_row = cur.execute(
                    "SELECT id FROM custom_components WHERE lower(display_name) = lower(?)",
                    (clean,)
                ).fetchone()
            if cust_row:
                return False, "Display Name already exists. (already assigned to another component). Enter a unique name or leave it empty."
                
            # 4. Check conflicting alias pointing to a DIFFERENT component
            if current_component_id:
                alias_row = cur.execute(
                    "SELECT component_id FROM component_aliases WHERE lower(alias) = lower(?) AND component_id != ?",
                    (clean, current_component_id)
                ).fetchone()
            else:
                alias_row = cur.execute(
                    "SELECT component_id FROM component_aliases WHERE lower(alias) = lower(?)",
                    (clean,)
                ).fetchone()
                
            if alias_row:
                return False, "Display Name already exists. (already assigned to another component). Enter a unique name or leave it empty."
                
        return True, "Valid display name."

    @staticmethod
    def assign_display_name(
        component_id: str,
        new_name: str,
        change_reason: Optional[str] = None,
        user: str = "admin",
        db_path: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """
        Assigns or updates a component's display name.
        """
        valid, msg = ComponentLibraryService.validate_display_name(new_name, component_id, db_path=db_path)
        if not valid:
            return False, msg
            
        clean_name = new_name.strip()
        now_str = datetime.now().isoformat()
        
        ensure_database_ready(db_path=db_path)
        conn = get_db_connection(db_path)
        try:
            with conn:
                cur = conn.cursor()
                
                comp = cur.execute("SELECT id, display_name, failure_rate_id FROM components WHERE id = ?", (component_id,)).fetchone()
                if not comp:
                    return False, f"Component with ID '{component_id}' not found."
                    
                old_name = comp["display_name"]
                action = "assign_display_name" if not old_name else "edit_display_name"
                
                # If editing an existing display name, only preserve old name as alias if NOT a test name
                if old_name and old_name != clean_name and not ComponentLibraryService.is_test_name(old_name):
                    existing_alias = cur.execute(
                        "SELECT id FROM component_aliases WHERE component_id = ? AND alias = ?",
                        (component_id, old_name)
                    ).fetchone()
                    if not existing_alias:
                        cur.execute("""
                            INSERT INTO component_aliases (component_id, alias, alias_type, created_at)
                            VALUES (?, ?, 'historical', ?)
                        """, (component_id, old_name, now_str))
                
                # Update display name
                cur.execute("""
                    UPDATE components 
                    SET display_name = ?, updated_at = ?
                    WHERE id = ?
                """, (clean_name, now_str, component_id))
                
                # Record in change log
                cur.execute("""
                    INSERT INTO component_change_log (
                        component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                    ) VALUES (?, ?, 'display_name', ?, ?, ?, ?, ?)
                """, (component_id, action, old_name, clean_name, change_reason or "Display name update", user, now_str))
                
            return True, f"Display name '{clean_name}' successfully assigned to component {comp['failure_rate_id']}."
        except Exception as e:
            conn.rollback()
            return False, f"Database transaction failed: {e}"
        finally:
            conn.close()

    @staticmethod
    def remove_display_name(
        component_id: str,
        change_reason: Optional[str] = None,
        user: str = "admin",
        db_path: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """
        Removes a component's display name, setting components.display_name = NULL.
        - Does not modify UUID, failure_rate_id, item_no, FIT values, failure modes, or source data.
        - If the removed name was a test name, cleans matching test aliases and audit entries.
        - If legitimate, records action='remove_display_name' in component_change_log.
        """
        ensure_database_ready(db_path=db_path)
        now_str = datetime.now().isoformat()
        conn = get_db_connection(db_path)
        try:
            with conn:
                cur = conn.cursor()
                comp = cur.execute("SELECT id, display_name, failure_rate_id, component_type FROM components WHERE id = ?", (component_id,)).fetchone()
                if not comp:
                    return False, f"Component with ID '{component_id}' not found."
                
                old_name = comp["display_name"]
                if not old_name:
                    return True, "Display name is already NULL."
                    
                # Update components table: set display_name = NULL
                cur.execute("UPDATE components SET display_name = NULL, updated_at = ? WHERE id = ?", (now_str, component_id))
                
                # Check if old name was a test name
                if ComponentLibraryService.is_test_name(old_name):
                    # Delete test aliases for this component matching the test name or test prefixes
                    cur.execute(
                        "DELETE FROM component_aliases WHERE component_id = ? AND (alias = ? OR alias LIKE 'TEST%' OR alias LIKE 'BATCH_TEST%')",
                        (component_id, old_name)
                    )
                    # Delete test-generated change log entries
                    cur.execute(
                        "DELETE FROM component_change_log WHERE component_id = ? AND (new_value LIKE 'TEST%' OR new_value LIKE 'BATCH_TEST%' OR old_value LIKE 'TEST%' OR old_value LIKE 'BATCH_TEST%')",
                        (component_id,)
                    )
                else:
                    # Record legitimate removal in change log
                    reason = change_reason or "Display name removed (restored to NULL)"
                    cur.execute("""
                        INSERT INTO component_change_log (
                            component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                        ) VALUES (?, 'remove_display_name', 'display_name', ?, NULL, ?, ?, ?)
                    """, (component_id, old_name, reason, user, now_str))
                    
            return True, f"Display name successfully removed for component {comp['failure_rate_id']}."
        except Exception as e:
            conn.rollback()
            return False, f"Failed to remove display name: {e}"
        finally:
            conn.close()

    @staticmethod
    def batch_assign_display_names(
        assignments: List[Dict[str, str]],
        user: str = "admin",
        db_path: Optional[Path] = None
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Validates and saves a batch of display name assignments.
        If ANY entry is invalid or duplicated, rolls back the entire batch.
        """
        if not assignments:
            return True, "No assignments to save.", []
            
        # 1. Validate complete batch upfront
        errors: List[Dict[str, Any]] = []
        proposed_names_seen: Dict[str, str] = {}  # name -> component_id
        
        for item in assignments:
            c_id = item.get("component_id")
            proposed_name = (item.get("proposed_display_name") or "").strip()
            
            if not c_id:
                errors.append({"component_id": "", "name": proposed_name, "error": "Missing component ID."})
                continue
                
            if not proposed_name:
                continue  # Blank entries are skipped in batch
                
            # Check internal duplicate within the batch
            if proposed_name in proposed_names_seen:
                errors.append({
                    "component_id": c_id,
                    "name": proposed_name,
                    "error": f"Duplicate proposed display name in batch (conflicts with component {proposed_names_seen[proposed_name]})."
                })
                continue
            proposed_names_seen[proposed_name] = c_id
            
            # Check validation rules against database
            valid, msg = ComponentLibraryService.validate_display_name(proposed_name, c_id, db_path=db_path)
            if not valid:
                errors.append({"component_id": c_id, "name": proposed_name, "error": msg})
                
        if errors:
            return False, f"Batch validation failed with {len(errors)} error(s).", errors
            
        # 2. Transactionally apply all assignments
        now_str = datetime.now().isoformat()
        ensure_database_ready(db_path=db_path)
        conn = get_db_connection(db_path)
        try:
            with conn:
                cur = conn.cursor()
                applied_count = 0
                
                for item in assignments:
                    c_id = item.get("component_id")
                    proposed_name = (item.get("proposed_display_name") or "").strip()
                    reason = item.get("change_reason", "Batch display name assignment")
                    
                    if not proposed_name or not c_id:
                        continue
                        
                    comp = cur.execute("SELECT id, display_name FROM components WHERE id = ?", (c_id,)).fetchone()
                    if not comp:
                        continue
                        
                    old_name = comp["display_name"]
                    action = "assign_display_name" if not old_name else "edit_display_name"
                    
                    if old_name and old_name != proposed_name and not ComponentLibraryService.is_test_name(old_name):
                        existing_alias = cur.execute(
                            "SELECT id FROM component_aliases WHERE component_id = ? AND alias = ?",
                            (c_id, old_name)
                        ).fetchone()
                        if not existing_alias:
                            cur.execute("""
                                INSERT INTO component_aliases (component_id, alias, alias_type, created_at)
                                VALUES (?, ?, 'historical', ?)
                            """, (c_id, old_name, now_str))
                    
                    cur.execute("UPDATE components SET display_name = ?, updated_at = ? WHERE id = ?", (proposed_name, now_str, c_id))
                    
                    cur.execute("""
                        INSERT INTO component_change_log (
                            component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                        ) VALUES (?, ?, 'display_name', ?, ?, ?, ?, ?)
                    """, (c_id, action, old_name, proposed_name, reason, user, now_str))
                    
                    applied_count += 1
                    
            return True, f"Successfully saved {applied_count} display name(s).", []
        except Exception as e:
            conn.rollback()
            return False, f"Batch save transaction failed: {e}", [{"error": str(e)}]
        finally:
            conn.close()

    @staticmethod
    def get_unassigned_display_names(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Returns Exida components where display_name is NULL."""
        ensure_database_ready(db_path=db_path)
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            rows = cur.execute("""
                SELECT 
                    id, failure_rate_id, item_id, item_no,
                    display_name, component_type, component_subtype,
                    component_use_category, mapping_status, status
                FROM components
                WHERE (display_name IS NULL OR trim(display_name) = '')
                  AND status = 'active'
                ORDER BY failure_rate_id ASC
            """).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def get_change_logs(component_id: Optional[str] = None, limit: int = 200, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Retrieves audit change log records."""
        ensure_database_ready(db_path=db_path)
        with get_db_connection(db_path) as conn:
            cur = conn.cursor()
            if component_id:
                rows = cur.execute("""
                    SELECT id, component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                    FROM component_change_log
                    WHERE component_id = ?
                    ORDER BY id DESC LIMIT ?
                """, (component_id, limit)).fetchall()
            else:
                rows = cur.execute("""
                    SELECT id, component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                    FROM component_change_log
                    ORDER BY id DESC LIMIT ?
                """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    @staticmethod
    def set_component_status(component_id: str, new_status: str, reason: str = "", user: str = "admin", db_path: Optional[Path] = None) -> Tuple[bool, str]:
        """Retires or reactivates an Exida or Legacy component."""
        if new_status not in ("active", "retired"):
            return False, "Status must be 'active' or 'retired'."
            
        ensure_database_ready(db_path=db_path)
        now_str = datetime.now().isoformat()
        conn = get_db_connection(db_path)
        try:
            with conn:
                cur = conn.cursor()
                # Check Exida
                exida = cur.execute("SELECT id, status FROM components WHERE id = ?", (component_id,)).fetchone()
                if exida:
                    old_status = exida["status"]
                    cur.execute("UPDATE components SET status = ?, updated_at = ? WHERE id = ?", (new_status, now_str, component_id))
                    cur.execute("""
                        INSERT INTO component_change_log (
                            component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                        ) VALUES (?, 'status_change', 'status', ?, ?, ?, ?, ?)
                    """, (component_id, old_status, new_status, reason or f"Component status changed to {new_status}", user, now_str))
                    return True, f"Component status changed to '{new_status}'."
                    
                # Check Legacy
                leg = cur.execute("SELECT id, status FROM legacy_components WHERE id = ?", (component_id,)).fetchone()
                if leg:
                    old_status = leg["status"]
                    cur.execute("UPDATE legacy_components SET status = ?, updated_at = ? WHERE id = ?", (new_status, now_str, component_id))
                    cur.execute("""
                        INSERT INTO component_change_log (
                            component_id, action, field_changed, old_value, new_value, change_reason, user, timestamp
                        ) VALUES (?, 'status_change', 'status', ?, ?, ?, ?, ?)
                    """, (component_id, old_status, new_status, reason or f"Legacy component status changed to {new_status}", user, now_str))
                    return True, f"Legacy component status changed to '{new_status}'."
                    
                return False, f"Component '{component_id}' not found."
        except Exception as e:
            conn.rollback()
            return False, f"Status update failed: {e}"
        finally:
            conn.close()
