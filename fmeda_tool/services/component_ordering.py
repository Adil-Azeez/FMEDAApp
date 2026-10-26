"""Read-only BOM blocks shared by the FMEDA table and Excel export."""
from collections import defaultdict
from dataclasses import dataclass
import re

from fmeda_tool.models import Component, Unit


@dataclass
class ComponentBlock:
    key: tuple[str, str]
    components: list[Component]


def natural_position_key(position: str):
    return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                 for part in re.split(r"(\d+)", position or ""))


def component_blocks(unit: Unit) -> list[ComponentBlock]:
    """Resolve stable mapping identities, then present blocks in imported order.

    The stored BOM sequence is the canonical import index, including old JSON.
    Source row_number is a physical TXT line and can restart across imports;
    it must not override that sequence. Nothing here modifies project objects.
    Models within one BOM record retain their persisted relative order.
    """
    bom_ids = {bom.id for bom in unit.bom_components}
    by_position = defaultdict(list)
    for bom in unit.bom_components:
        by_position[bom.designator.strip().casefold()].append(bom.id)
    mapped = {m.component_instance_id: m.bom_component_id
              for m in unit.component_mappings if m.component_instance_id}
    groups = defaultdict(list)
    unlinked = []
    for component in unit.components:
        if component.id in mapped:
            bom_id = mapped[component.id]
        else:
            # Legacy/manual instances may predate explicit mapping identities.
            matches = by_position.get(component.position.strip().casefold(), [])
            bom_id = matches[0] if len(matches) == 1 else None
        if bom_id in bom_ids:
            groups[bom_id].append(component)
        else:
            unlinked.append(component)
    blocks = [ComponentBlock(("bom", bom.id), groups[bom.id])
              for bom in unit.bom_components if groups[bom.id]]
    # Python's stable sort retains persisted relative order for equivalent names.
    blocks.extend(ComponentBlock(("component", c.id), [c])
                  for c in sorted(unlinked, key=lambda c: natural_position_key(c.position)))
    return blocks


def ordered_components(unit: Unit) -> list[Component]:
    return [component for block in component_blocks(unit) for component in block.components]


def ordered_mappings(unit: Unit):
    """Order the Excel identity ledger too, retaining unresolved mapping records."""
    bom_index = {bom.id: index for index, bom in enumerate(unit.bom_components)}
    instances = {component.id: index for index, component in enumerate(ordered_components(unit))}
    return sorted(unit.component_mappings, key=lambda mapping: (
        bom_index.get(mapping.bom_component_id, len(bom_index)),
        instances.get(mapping.component_instance_id, len(instances))))
