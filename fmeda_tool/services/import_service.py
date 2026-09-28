import json
import re
from typing import List, Dict, Tuple, Any, Optional
import uuid
from fmeda_tool.models.bom_component import BOMComponent


def format_value_description(wert: Optional[str], beschreibung: Optional[str]) -> str:
    """
    Combines Wert and Beschreibung for FMEDA Value / Description field according to rules:
    - Both present: Wert / Beschreibung
    - Only Wert present: Wert
    - Only Beschreibung present: Beschreibung
    - Both absent: Empty string
    - Trims whitespace, avoids duplicate leading Wert in Beschreibung, removes 'None'/'null' text.
    """
    w = (wert or "").strip()
    b = (beschreibung or "").strip()
    
    # Filter out literal string 'None' or 'null'
    if w.lower() in ("none", "null"):
        w = ""
    if b.lower() in ("none", "null"):
        b = ""
        
    if w and b:
        # Check if description already starts with exact value to avoid duplication
        if b.startswith(w) and (len(b) == len(w) or b[len(w)] in (" ", "/", "-", ",", ";")):
            return b
        return f"{w} / {b}"
    elif w:
        return w
    elif b:
        return b
    return ""


class ImportService:
    """Service to handle parsing, schema validation, and duplicate checking for fixed-width BOM TXT files"""
    
    @staticmethod
    def format_value_description(wert: Optional[str], beschreibung: Optional[str]) -> str:
        """Expose format_value_description as static method on ImportService."""
        return format_value_description(wert, beschreibung)
    
    @staticmethod
    def parse_bom_txt(
        txt_content: str, 
        existing_designators: Optional[List[str]] = None, 
        filepath: Optional[str] = None
    ) -> Tuple[List[BOMComponent], List[str], List[str]]:
        """
        Parses fixed-width BOM text content and performs validation.
        
        Args:
            txt_content: The raw text string containing fixed-width BOM table data.
            existing_designators: Optional list of designators already in the project/unit.
            filepath: Optional source TXT file path.
            
        Returns:
            A tuple of (parsed_components, errors, warnings)
        """
        parsed_components: List[BOMComponent] = []
        errors: List[str] = []
        warnings: List[str] = []
        
        if txt_content.startswith('\ufeff'):
            txt_content = txt_content[1:]
            
        lines = txt_content.splitlines()
        if not lines or all(not line.strip() for line in lines):
            errors.append("Empty BOM text file.")
            return [], errors, warnings
            
        # Aliases mapping for fixed-width headers
        HEADER_ALIASES = {
            "vs": ["vs", "v", "version", "rev", "status"],
            "pos": ["pos", "pos.", "position", "designator", "bauteil", "ref", "refdes", "kks"],
            "mn": ["mn", "mat.-nr.", "mat-nr", "matnr", "materialnummer", "material-nr", "material_number", "part_number", "part number", "teilenummer", "tn", "art.-nr.", "artikelnummer", "sachnummer"],
            "benennung": ["benennung", "bezeichnung", "art", "component_type", "type", "typ", "kategorie", "category"],
            "wert": ["wert", "value", "val"],
            "beschreibung": ["beschreibung", "description", "desc", "bezeichnung2"],
            "bemerkung": ["bemerkung", "bemerkungen", "note", "notes", "kommentar", "hinweis", "hinweise"],
            "lage": ["lage", "layer", "seite", "bestückungsseite", "bestueckungsseite", "ebene"]
        }
        
        # 1. Detect header row
        header_row_idx = -1
        col_slices: Dict[str, Tuple[int, Optional[int]]] = {}
        
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue
                
            # Ignore lines that are obvious comments or separators
            if re.match(r"^[-=\s_#*]+$", line_str) or line_str.startswith(("//", "/*", "--", "#")):
                continue
                
            # Scan tokens and find positions
            # We search for matches of any alias in the line
            found_headers: List[Tuple[str, int, int]] = []  # (canonical_name, start, end)
            
            # Use regex to find word tokens or symbols
            token_matches = list(re.finditer(r"[^\s]+", line))
            # Also support 2-word tokens like "Part Number", "Mat.-Nr."
            i = 0
            while i < len(token_matches):
                t_match = token_matches[i]
                token_text = t_match.group(0).lower()
                
                # Check 2-word combination first
                matched_2word = False
                if i + 1 < len(token_matches):
                    two_words = f"{token_text} {token_matches[i+1].group(0).lower()}"
                    for key, aliases in HEADER_ALIASES.items():
                        if two_words in [a.lower() for a in aliases]:
                            start_pos = t_match.start()
                            end_pos = token_matches[i+1].end()
                            found_headers.append((key, start_pos, end_pos))
                            matched_2word = True
                            i += 2
                            break
                if matched_2word:
                    continue
                    
                # Check single token
                clean_token = token_text.rstrip(":")
                for key, aliases in HEADER_ALIASES.items():
                    if clean_token in [a.lower() for a in aliases]:
                        found_headers.append((key, t_match.start(), t_match.end()))
                        break
                i += 1
                
            # A valid header row MUST contain "pos" and at least one other known BOM column
            header_keys = {h[0] for h in found_headers}
            if "pos" in header_keys and len(header_keys) >= 2:
                header_row_idx = idx
                # Sort by start index
                found_headers.sort(key=lambda x: x[1])
                
                # Build column slices
                for h_idx, (col_name, start, end) in enumerate(found_headers):
                    next_start = found_headers[h_idx + 1][1] if h_idx + 1 < len(found_headers) else None
                    col_slices[col_name] = (start, next_start)
                break
                
        if header_row_idx == -1 or "pos" not in col_slices:
            errors.append("Missing fixed-width header row with 'Pos' column.")
            return [], errors, warnings
            
        # 2. Parse data rows
        if existing_designators is None:
            existing_designators = []
        existing_set = {d.strip().upper() for d in existing_designators}
        seen_in_file: Dict[str, Tuple[int, str, str, str, str, str]] = {}
        
        def extract_field(line_text: str, col_key: str) -> str:
            if col_key not in col_slices:
                return ""
            start, end = col_slices[col_key]
            if start >= len(line_text):
                return ""
                
            # Dynamic word-boundary refinement for slight column misalignments
            eff_start = start
            if start > 0 and start < len(line_text):
                if line_text[start] != ' ' and line_text[start - 1] != ' ':
                    ws = start
                    while ws > 0 and line_text[ws - 1] != ' ':
                        ws -= 1
                    if ws > 0 and line_text[ws - 1] == ' ':
                        eff_start = ws
                        
            eff_end = end
            if end is not None and end < len(line_text):
                if line_text[end] != ' ' and line_text[end - 1] != ' ':
                    ws = end
                    while ws > eff_start and line_text[ws - 1] != ' ':
                        ws -= 1
                    if ws > eff_start and line_text[ws - 1] == ' ':
                        eff_end = ws
                        
            if eff_end is not None:
                return line_text[eff_start:eff_end].strip()
            else:
                return line_text[eff_start:].strip()
                
        for line_idx, line in enumerate(lines[header_row_idx + 1:], start=header_row_idx + 2):
            raw_line = line
            stripped = line.strip()
            if not stripped:
                continue
                
            # Check for LIST END or end of table marker
            if re.search(r"\bLIST\s+END\b|\bEND\s+OF\s+LIST\b|\*\*\*\s*END\s*\*\*\*", stripped, re.IGNORECASE):
                break
                
            # Skip separator lines
            if re.match(r"^[-=\s_#*]+$", stripped) or stripped.startswith(("//", "/*", "--", "#")):
                continue
                
            # Skip page headers/footers
            if re.match(r"^(Seite|Page)\s+\d+(\s+(von|of)\s+\d+)?", stripped, re.IGNORECASE):
                continue
                
            # Skip document metadata lines if repeated
            if any(stripped.startswith(prefix) for prefix in ["Projekt:", "Project:", "Datum:", "Date:", "Author:", "Revision:"]):
                continue
                
            pos = extract_field(raw_line, "pos")
            mn = extract_field(raw_line, "mn")
            benennung = extract_field(raw_line, "benennung")
            wert = extract_field(raw_line, "wert")
            beschreibung = extract_field(raw_line, "beschreibung")
            bemerkung = extract_field(raw_line, "bemerkung")
            lage = extract_field(raw_line, "lage")
            vs = extract_field(raw_line, "vs")
            
            # If all extracted fields are empty, line has no component data
            if not pos and not mn and not benennung and not wert and not beschreibung and not bemerkung and not lage:
                continue
                
            # Required Pos validation
            if not pos:
                errors.append(f"Line {line_idx}: Missing required Pos value. Original line: '{raw_line}'")
                continue
                
            pos_upper = pos.upper()
            
            # Duplicate Pos inside the file validation
            if pos_upper in seen_in_file:
                prev_line, prev_mn, prev_w, prev_b, prev_l, prev_raw = seen_in_file[pos_upper]
                errors.append(
                    f"Line {line_idx}: Duplicate Pos '{pos}' found. "
                    f"Previous instance at Line {prev_line} (MN: '{prev_mn}', Wert: '{prev_w}', Beschreibung: '{prev_b}', Lage: '{prev_l}'). "
                    f"Current line: '{raw_line}'"
                )
                continue
            else:
                seen_in_file[pos_upper] = (line_idx, mn, wert, beschreibung, lage, raw_line)
                
            # Duplicate Pos against existing functional group data
            if pos_upper in existing_set:
                warnings.append(f"Line {line_idx}: Duplicate Pos '{pos}' against existing functional-group data.")
                
            # Fitted status checking (e.g. 'nicht bestueckt', 'nicht bestückt')
            is_fitted = True
            bemerkung_norm = bemerkung.lower()
            not_fitted_keywords = ["nicht bestueckt", "nicht bestückt", "not fitted", "not_fitted", "dnp", "do not populate"]
            if any(kw in bemerkung_norm for kw in not_fitted_keywords):
                is_fitted = False
                warnings.append(f"Line {line_idx} ({pos}): Component is marked as Not Fitted ('{bemerkung}').")
                
            comp_id = f"bom_{uuid.uuid4().hex[:8]}"
            layer = lage or "TOP"
            
            try:
                comp = BOMComponent(
                    id=comp_id,
                    designator=pos,
                    part_number=mn,
                    description=beschreibung or None,
                    value=wert or None,
                    benennung=benennung or None,
                    layer=layer,
                    notes=bemerkung or None,
                    vs=vs or None,
                    package=None,
                    quantity=1,
                    is_fitted=is_fitted,
                    function=benennung or None,
                    internal_part_number=mn or None,
                    manufacturer=None,
                    manufacturer_part_number=None,
                    location=None,
                    source_file=filepath or None,
                    row_number=line_idx,
                    original_line=raw_line
                )
                parsed_components.append(comp)
            except Exception as e:
                errors.append(f"Line {line_idx} ({pos}): Validation error: {str(e)}")
                
        if not parsed_components and not errors:
            errors.append("No valid component records found in BOM text file.")
            
        return parsed_components, errors, warnings

