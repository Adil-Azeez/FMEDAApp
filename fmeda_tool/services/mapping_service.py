from typing import List, Dict, Tuple, Optional
from fmeda_tool.models import BOMComponent, ComponentDB, ComponentMapping


class MappingService:
    """Service to automatically map BOM components to database templates with confidence scoring"""
    
    @staticmethod
    def calculate_confidence(bom: BOMComponent, db: ComponentDB) -> float:
        """
        Calculates a matching confidence score (0.0 to 1.0) between a BOM component and a DB template.
        """
        # Standardize strings for robust matching
        pn = (bom.part_number or "").strip().lower()
        desc = (bom.description or "").strip().lower()
        val = (bom.value or "").strip().lower()
        
        db_disp = (db.display_name or "").strip().lower()
        db_short = (db.shortcut or "").strip().lower()
        
        # 1. Designator prefix matching boost
        import re
        des_match = re.match(r'^([a-zA-Z]+)', bom.designator)
        des_prefix = des_match.group(1).lower() if des_match else ""
        prefix_match = False
        if des_prefix and db_short:
            if db_short.lower() == des_prefix:
                prefix_match = True
            elif db_short.lower().startswith(des_prefix) or des_prefix.startswith(db_short.lower()):
                prefix_match = True

        # 2. Exact match on part number to shortcut or display name
        if pn and (pn == db_short or pn == db_disp):
            return 1.0
            
        # 3. Perfect value match combined with category keyword
        if val:
            val_clean = val.replace(" ", "")
            db_disp_clean = db_disp.replace(" ", "")
            db_short_clean = db_short.replace(" ", "")
            
            is_val_match = (val_clean in db_disp_clean) or (val_clean in db_short_clean)
            
            # Category match (Resistor / Capacitor / Transistor / Diode / Inductor)
            is_cat_match = False
            for kw, db_kws in [
                ("res", ["resistor", "res"]),
                ("cap", ["capacitor", "cap"]),
                ("trans", ["transistor", "bjt", "mosfet", "trans"]),
                ("diode", ["diode", "led"]),
                ("ind", ["inductor", "ferrite", "ind"])
            ]:
                if kw in desc or kw in pn:
                    if any(dkw in db_disp or dkw in db_short for dkw in db_kws):
                        is_cat_match = True
                        break
                        
            if is_val_match and is_cat_match:
                return 0.90
            elif is_val_match:
                return 0.70
            elif is_cat_match:
                return 0.40
                
        # 4. Substring match on description
        if desc and (desc in db_disp or db_disp in desc):
            score = 0.50
        else:
            score = 0.10
            
        if prefix_match:
            score = max(score, 0.35)
            
        return score

    @staticmethod
    def get_suggestions(bom: BOMComponent, db_list: List[ComponentDB]) -> List[Tuple[ComponentDB, float]]:
        """
        Returns all DB templates sorted by matching confidence score.
        """
        suggestions = []
        for db in db_list:
            score = MappingService.calculate_confidence(bom, db)
            suggestions.append((db, score))
        # Sort by score descending
        suggestions.sort(key=lambda x: x[1], reverse=True)
        return suggestions
        
    @staticmethod
    def auto_map_bom(bom_list: List[BOMComponent], db_list: List[ComponentDB]) -> List[ComponentMapping]:
        """
        Auto-generates mappings for all BOM components using the highest-scoring candidate.
        """
        mappings = []
        for bom in bom_list:
            suggestions = MappingService.get_suggestions(bom, db_list)
            if suggestions:
                best_db, confidence = suggestions[0]
                is_confirmed = (confidence >= 0.90)
                mappings.append(ComponentMapping(
                    bom_component_id=bom.id,
                    component_db_id=best_db.id,
                    confidence=confidence,
                    is_confirmed=is_confirmed
                ))
        return mappings
