import re
from typing import List, Dict, Tuple, Optional, Set
from fmeda_tool.models import BOMComponent, ComponentDB, ComponentMapping


class MappingService:
    """Service to map BOM components to database templates with confidence scoring and reusable MN mapping"""

    @staticmethod
    def prepare_batch(unit, additions=(), removals=(), replacements=None, profile="Profile 1", project=None):
        """Return a validated candidate; every error leaves the input unit untouched."""
        from uuid import uuid4
        from fmeda_tool.models import Unit
        from fmeda_tool.services.component_remapping_service import ComponentRemappingService, library_identity
        candidate = Unit.model_validate(unit.model_dump())
        replacements = replacements or {}
        removed = set(removals)
        existing = {m.id: m for m in candidate.component_mappings}
        if (removed | set(replacements)) - existing.keys():
            raise ValueError("The selected mapping no longer exists.")
        removed_components = {existing[mid].component_instance_id for mid in removed}
        candidate.component_mappings = [m for m in candidate.component_mappings if m.id not in removed]
        candidate.components = [c for c in candidate.components if c.id not in removed_components
                                and c.position not in ("Mapping Template", "Template") and not c.is_template]
        for mapping_id, component in replacements.items():
            if mapping_id in removed:
                raise ValueError("Cannot remove and remap the same mapping.")
            mapping = existing[mapping_id]
            if component.id != mapping.component_instance_id:
                raise ValueError("Remapping must preserve the component-instance identity.")
            index = next((i for i, c in enumerate(candidate.components) if c.id == component.id), None)
            if index is None:
                raise ValueError("Mapped component instance is missing.")
            candidate.components[index] = component.model_copy(deep=True)
            prior = {"library_source": mapping.library_source, "component_db_id": mapping.component_db_id}
            mapping.component_db_id = component.library_component_id
            mapping.library_source = component.source_type
            mapping.metadata = {**mapping.metadata, "remapped_from": prior}
        pairs = [m.pair for m in candidate.component_mappings]
        if len(pairs) != len(set(pairs)):
            raise ValueError("This BOM record and library component are already mapped.")
        by_bom = {b.id: b for b in candidate.bom_components}
        for bom_id, template in additions:
            if bom_id not in by_bom:
                raise ValueError("The BOM record no longer exists.")
            source, library_id = library_identity(template)
            pair = (bom_id, source, library_id)
            prior = next((m for m in candidate.component_mappings if m.pair == pair), None)
            if prior and any(c.id == prior.component_instance_id for c in candidate.components):
                continue  # Repeated Save Mappings is idempotent.
            bom = by_bom[bom_id]
            component = ComponentRemappingService.plan(None, template, bom, profile, project).component
            candidate.components.append(component)
            if prior:
                prior.component_instance_id = component.id
                prior.bom_position = bom.designator
                continue
            candidate.component_mappings.append(ComponentMapping(
                id="map_" + uuid4().hex, bom_component_id=bom.id, bom_position=bom.designator,
                component_db_id=library_id, library_source=source, component_instance_id=component.id,
                confidence=1.0, is_confirmed=True,
                metadata={"profile": profile, "bom": bom.model_dump(mode="json")}))
            pairs.append(pair)
        return Unit.model_validate(candidate.model_dump())

    @staticmethod
    def commit_batch(unit, candidate):
        """One mutation boundary; reuse untouched instances for targeted table refresh."""
        from fmeda_tool.models import Unit
        checked = Unit.model_validate(candidate.model_dump())
        previous = {c.id: c for c in unit.components}
        checked.components = [
            previous[c.id] if c.id in previous and previous[c.id].model_dump() == c.model_dump() else c
            for c in checked.components]
        changed = {c.id for c in checked.components if c.id not in previous or c is not previous[c.id]}
        changed.update(set(previous) - {c.id for c in checked.components})
        unit.__dict__.update(checked.__dict__)
        return changed
    
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
