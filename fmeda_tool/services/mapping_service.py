import re
from typing import List, Dict, Tuple, Optional, Set
from fmeda_tool.models import BOMComponent, ComponentDB, ComponentMapping


class MappingService:
    """Service to map BOM components to database templates with confidence scoring and reusable MN mapping"""
    
    @staticmethod
    def calculate_confidence(
        bom: BOMComponent, 
        db: ComponentDB, 
        approved_mn_mappings: Optional[Dict[str, str]] = None
    ) -> float:
        """
        Calculates a matching confidence score (0.0 to 1.0) between a BOM component and a DB template.
        Prioritizes approved Material Number (MN) mappings.
        """
        pn = (bom.internal_part_number or bom.part_number or "").strip().lower()
        benennung = (getattr(bom, "benennung", None) or getattr(bom, "function", None) or "").strip().lower()
        desc = (bom.description or "").strip().lower()
        val = (bom.value or "").strip().lower()
        
        db_disp = (db.display_name or "").strip().lower()
        db_short = (db.shortcut or "").strip().lower()
        db_mat = (db.material or "").strip().lower()
        db_id = (db.id or "").strip().lower()
        
        # 1. Approved MN (Material Number) mapping match
        if approved_mn_mappings and pn:
            approved_target = approved_mn_mappings.get(pn.upper()) or approved_mn_mappings.get(pn)
            if approved_target and (approved_target.lower() == db_id or approved_target.lower() == db_disp):
                return 1.0
                
        # 2. Exact match on part number / MN to template shortcut or display name or ID
        if pn and (pn == db_short or pn == db_disp or pn == db_id):
            return 1.0
            
        # 3. Designator prefix matching boost
        des_match = re.match(r'^([a-zA-Z]+)', bom.designator)
        des_prefix = des_match.group(1).lower() if des_match else ""
        prefix_match = False
        if des_prefix and db_short:
            if db_short.lower() == des_prefix:
                prefix_match = True
            elif db_short.lower().startswith(des_prefix) or des_prefix.startswith(db_short.lower()):
                prefix_match = True
                
        # 4. Category / Benennung match keywords
        is_cat_match = False
        cat_keywords = [
            ("res", ["resistor", "res", "widerstand", "metal film", "dickschicht"]),
            ("cap", ["capacitor", "cap", "kondensator", "keramik", "elko", "tantal"]),
            ("trans", ["transistor", "bjt", "mosfet", "trans", "fet", "igbt"]),
            ("diode", ["diode", "led", "zener", "gleichrichter", "schottky"]),
            ("ind", ["inductor", "ferrite", "ind", "drossel", "spule"]),
            ("ic", ["ic", "opv", "opamp", "microcontroller", "controller", "komparator", "treiber", "driver"])
        ]
        
        combined_text = f"{benennung} {desc} {pn}".lower()
        for kw, db_kws in cat_keywords:
            if any(k in combined_text for k in [kw] + db_kws):
                if any(dkw in db_disp or dkw in db_short or dkw in db_mat for dkw in db_kws):
                    is_cat_match = True
                    break
                    
        # 5. Value matching
        if val:
            val_clean = val.replace(" ", "")
            db_disp_clean = db_disp.replace(" ", "")
            db_short_clean = db_short.replace(" ", "")
            
            is_val_match = (val_clean in db_disp_clean) or (val_clean in db_short_clean)
            
            if is_val_match and is_cat_match:
                return 0.90
            elif is_val_match:
                return 0.70
            elif is_cat_match:
                return 0.40
                
        # 6. Description / Benennung Substring match
        if desc and (desc in db_disp or db_disp in desc):
            score = 0.50
        elif benennung and (benennung in db_disp or db_disp in benennung or benennung in db_mat):
            score = 0.45
        else:
            score = 0.10
            
        if prefix_match:
            score = max(score, 0.35)
            
        return score

    @staticmethod
    def get_suggestions(
        bom: BOMComponent, 
        db_list: List[ComponentDB],
        approved_mn_mappings: Optional[Dict[str, str]] = None
    ) -> List[Tuple[ComponentDB, float]]:
        """
        Returns all DB templates sorted by matching confidence score.
        """
        suggestions = []
        for db in db_list:
            score = MappingService.calculate_confidence(bom, db, approved_mn_mappings=approved_mn_mappings)
            suggestions.append((db, score))
        # Sort by score descending
        suggestions.sort(key=lambda x: x[1], reverse=True)
        return suggestions
        
    @staticmethod
    def auto_map_bom(
        bom_list: List[BOMComponent], 
        db_list: List[ComponentDB],
        approved_mn_mappings: Optional[Dict[str, str]] = None
    ) -> List[ComponentMapping]:
        """
        Auto-generates mappings for all BOM components using the highest-scoring candidate.
        Only exact / approved MN matches (score == 1.0) are auto-confirmed.
        Fuzzy matches require explicit user confirmation.
        """
        mappings = []
        for bom in bom_list:
            suggestions = MappingService.get_suggestions(bom, db_list, approved_mn_mappings=approved_mn_mappings)
            if suggestions:
                best_db, confidence = suggestions[0]
                is_confirmed = (confidence >= 1.0)
                mappings.append(ComponentMapping(
                    bom_component_id=bom.id,
                    component_db_id=best_db.id,
                    confidence=confidence,
                    is_confirmed=is_confirmed
                ))
        return mappings
