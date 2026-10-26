from typing import Optional, Dict, Any
from uuid import uuid5, NAMESPACE_URL
from pydantic import BaseModel, Field


class ComponentMapping(BaseModel):
    """Binds a physical BOM component to a database component failure model template"""
    
    bom_component_id: str = Field(description="ID of the BOM component instance")
    component_db_id: str = Field(description="ID of the matched ComponentDB database template")
    id: str = ""
    bom_position: str = ""
    library_source: Optional[str] = None
    component_instance_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, description="Matching confidence score (0.0 to 1.0)")
    is_confirmed: bool = Field(default=False, description="Whether the mapping has been verified by the user")

    @property
    def pair(self):
        source = self.library_source or "exida"
        if source.casefold() in ("exida", "legacy", "custom"):
            source = source.casefold()
        return (self.bom_component_id, source, self.component_db_id)


def complete_mapping_identities(unit):
    """Deterministic in-memory migration; never writes files or changes assessments."""
    bom_by_id = {b.id: b for b in unit.bom_components}
    linked = {m.component_instance_id for m in unit.component_mappings if m.component_instance_id}
    for mapping in unit.component_mappings:
        bom = bom_by_id.get(mapping.bom_component_id)
        component = next((c for c in unit.components if c.id == mapping.component_instance_id), None)
        if component is None and bom:
            candidates = [c for c in unit.components if c.id not in linked
                          and c.position.casefold() == bom.designator.casefold()
                          and (c.library_component_id or c.id) == mapping.component_db_id
                          and (not mapping.library_source or c.source_type == mapping.library_source)]
            if len(candidates) == 1:
                component = candidates[0]
                mapping.component_instance_id = component.id
                linked.add(component.id)
        mapping.bom_position = mapping.bom_position or (bom.designator if bom else "")
        mapping.library_source = mapping.library_source or (component.source_type if component else None) or "exida"
        if not mapping.id:
            key = (unit.id, *mapping.pair, mapping.component_instance_id or "")
            mapping.id = "map_" + uuid5(NAMESPACE_URL, repr(key)).hex
    for component in unit.components:
        if component.id in linked or not component.library_component_id or component.is_template:
            continue
        boms = [b for b in unit.bom_components if b.designator.casefold() == component.position.casefold()]
        if len(boms) != 1:
            continue
        bom = boms[0]
        source = component.source_type or "exida"
        pair = (bom.id, source, component.library_component_id)
        if any(m.pair == pair for m in unit.component_mappings):
            continue
        unit.component_mappings.append(ComponentMapping(
            id="map_" + uuid5(NAMESPACE_URL, repr((unit.id, *pair, component.id))).hex,
            bom_component_id=bom.id, bom_position=bom.designator,
            component_db_id=component.library_component_id, library_source=source,
            component_instance_id=component.id, confidence=1, is_confirmed=True))
    return unit
