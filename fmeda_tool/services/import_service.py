import json
from typing import List, Dict, Tuple, Any, Optional
import uuid
from fmeda_tool.models.bom_component import BOMComponent


class ImportService:
    """Service to handle parsing, schema validation, and duplicate checking for CSV BOM files"""
    
    @staticmethod
    def parse_bom_csv(
        csv_content: str, 
        existing_designators: Optional[List[str]] = None, 
        filepath: Optional[str] = None
    ) -> Tuple[List[BOMComponent], List[str], List[str]]:
        """
        Parses BOM CSV content and performs validation.
        
        Args:
            csv_content: The raw CSV string containing BOM components.
            existing_designators: Optional list of designators already in the project/unit.
            filepath: Optional source CSV file path.
            
        Returns:
            A tuple of (parsed_components, errors, warnings)
        """
        import csv
        import io
        import uuid
        
        parsed_components: List[BOMComponent] = []
        errors: List[str] = []
        warnings: List[str] = []
        
        if csv_content.startswith('\ufeff'):
            csv_content = csv_content[1:]
        
        # Helper to parse fitted values
        def parse_fitted_value(val: str) -> Tuple[bool, Optional[str]]:
            val_norm = val.strip().lower()
            if not val_norm:
                return True, None
            true_options = ["true", "yes", "1", "fitted", "bestückt", "bestueckt"]
            false_options = ["false", "no", "0", "not fitted", "not_fitted", "nicht bestückt", "nicht bestueckt", "dnp", "do not populate"]
            if val_norm in true_options:
                return True, None
            elif val_norm in false_options:
                return False, None
            else:
                return True, f"Unrecognized fitted value '{val}'. Assuming Fitted."
        
        # 1. Delimiter detection
        lines = [line for line in csv_content.splitlines() if line.strip()]
        if not lines:
            errors.append("Empty CSV.")
            return [], errors, warnings
            
        first_line = lines[0]
        comma_count = first_line.count(',')
        semicolon_count = first_line.count(';')
        
        if comma_count == 0 and semicolon_count == 0:
            # Check the whole content
            all_commas = csv_content.count(',')
            all_semis = csv_content.count(';')
            if all_commas > 0 and all_semis == 0:
                delim = ','
            elif all_semis > 0 and all_commas == 0:
                delim = ';'
            else:
                delim = ','  # Default fallback
        elif comma_count > 0 and semicolon_count == 0:
            delim = ','
        elif semicolon_count > 0 and comma_count == 0:
            delim = ';'
        else:
            # Both present in header. Parse and compare column count.
            def match_score(d):
                try:
                    cols = next(csv.reader([first_line], delimiter=d))
                    return sum(1 for c in cols if c.strip())
                except Exception:
                    return 0
            score_comma = match_score(',')
            score_semi = match_score(';')
            delim = ',' if score_comma >= score_semi else ';'
            
        # 2. Parse CSV rows
        try:
            f = io.StringIO(csv_content)
            reader = csv.reader(f, delimiter=delim)
            rows = list(reader)
        except Exception as e:
            errors.append(f"Invalid CSV structure: {str(e)}")
            return [], errors, warnings
            
        if not rows:
            errors.append("Empty CSV.")
            return [], errors, warnings
            
        headers = [h.strip() for h in rows[0]]
        if not headers or all(not h for h in headers):
            errors.append("Missing header row.")
            return [], errors, warnings
            
        # Aliases mapping
        ALIASES = {
            "designator": ["designator", "component", "component_id", "position", "pos", "bauteil", "reference", "refdes"],
            "function": ["function", "funktion"],
            "value": ["value", "wert"],
            "description": ["description", "beschreibung", "value_description", "value / description", "wert / beschreibung"],
            "internal_part_number": ["internal_part_number", "part_number", "internal_pn", "material_number", "teilenummer", "tn"],
            "manufacturer": ["manufacturer", "hersteller"],
            "manufacturer_part_number": ["manufacturer_part_number", "manufacturer_pn", "herstellerteilenummer"],
            "layer": ["layer", "lage"],
            "location": ["location", "ort"],
            "fitted": ["fitted", "fitted_status", "status", "bestückt", "bestueckt"],
            "notes": ["notes", "note", "comments", "bemerkung", "bemerkungen"]
        }
        
        col_mapping = {}
        for idx, h in enumerate(headers):
            norm_h = h.strip().lower()
            for key, aliases in ALIASES.items():
                if norm_h in [a.lower() for a in aliases]:
                    if key not in col_mapping:
                        col_mapping[key] = idx
                    break
                    
        # Check required designator column
        if "designator" not in col_mapping:
            errors.append("Missing designator column.")
            return [], errors, warnings
            
        # Warn for missing optional columns
        missing_optionals = []
        optional_keys = [
            "function", "value", "description", "internal_part_number", 
            "manufacturer", "manufacturer_part_number", "layer", "location", 
            "fitted", "notes"
        ]
        for key in optional_keys:
            if key not in col_mapping:
                display_name = key.replace("_", " ").title()
                missing_optionals.append(display_name)
        if missing_optionals:
            warnings.append(f"Missing optional columns: {', '.join(missing_optionals)}")
            
        # Warn for unsupported extra columns
        unsupported_cols = []
        for h in headers:
            if not h.strip():
                continue
            norm_h = h.strip().lower()
            matched = False
            for key, aliases in ALIASES.items():
                if norm_h in [a.lower() for a in aliases]:
                    matched = True
                    break
            if not matched:
                unsupported_cols.append(h)
        if unsupported_cols:
            warnings.append(f"Unsupported extra columns ignored: {', '.join(unsupported_cols)}")
            
        # Duplicate sets
        if existing_designators is None:
            existing_designators = []
        existing_set = {d.strip().upper() for d in existing_designators}
        seen_in_file = set()
        
        for row_idx, row in enumerate(rows[1:], start=2):
            if not row or all(not cell.strip() for cell in row):
                continue
                
            if len(row) != len(headers):
                errors.append(f"Row {row_idx}: Invalid CSV structure (column count mismatch: expected {len(headers)}, got {len(row)}).")
                continue
                
            des_idx = col_mapping["designator"]
            if des_idx >= len(row):
                errors.append(f"Row {row_idx}: Missing designator cell.")
                continue
                
            designator_str = row[des_idx].strip()
            if not designator_str:
                errors.append(f"Row {row_idx}: Empty designator in a data row.")
                continue
                
            designator_upper = designator_str.upper()
            
            # Duplicate designator in the CSV
            if designator_upper in seen_in_file:
                errors.append(f"Row {row_idx}: Duplicate designator '{designator_str}' found inside the CSV.")
            else:
                seen_in_file.add(designator_upper)
                
            # Duplicate designator against existing functional-group data
            if designator_upper in existing_set:
                warnings.append(f"Row {row_idx}: Duplicate designator '{designator_str}' against existing functional-group data.")
                
            # Helper to retrieve cell values safely
            def get_cell(k):
                if k in col_mapping:
                    c_idx = col_mapping[k]
                    if c_idx < len(row):
                        return row[c_idx].strip()
                return ""
                
            func = get_cell("function")
            val = get_cell("value")
            desc = get_cell("description")
            internal_pn = get_cell("internal_part_number")
            mfr = get_cell("manufacturer")
            mfr_pn = get_cell("manufacturer_part_number")
            layer = get_cell("layer") or "TOP"
            loc = get_cell("location")
            fitted_val = get_cell("fitted")
            notes = get_cell("notes")
            
            # Check empty optional fields
            empty_opts = []
            for k in optional_keys:
                if k in col_mapping:
                    if not get_cell(k):
                        empty_opts.append(k.replace("_", " ").title())
            if empty_opts:
                warnings.append(f"Row {row_idx}: Empty optional fields: {', '.join(empty_opts)}")
                
            # Fitted value normalization
            is_fitted, fit_warn = parse_fitted_value(fitted_val)
            if fit_warn:
                warnings.append(f"Row {row_idx}: {fit_warn}")
                
            comp_id = f"bom_{uuid.uuid4().hex[:8]}"
            part_number = internal_pn or mfr_pn or ""
            
            try:
                comp = BOMComponent(
                    id=comp_id,
                    designator=designator_str,
                    part_number=part_number,
                    description=desc or None,
                    value=val or None,
                    package=None,
                    layer=layer,
                    quantity=1,
                    is_fitted=is_fitted,
                    notes=notes or None,
                    function=func or None,
                    internal_part_number=internal_pn or None,
                    manufacturer=mfr or None,
                    manufacturer_part_number=mfr_pn or None,
                    location=loc or None,
                    source_file=filepath or None,
                    row_number=row_idx
                )
                parsed_components.append(comp)
            except Exception as e:
                errors.append(f"Row {row_idx} ({designator_str}): Validation error: {str(e)}")
                
        if not parsed_components and not errors:
            errors.append("No valid component rows.")
            
        return parsed_components, errors, warnings
