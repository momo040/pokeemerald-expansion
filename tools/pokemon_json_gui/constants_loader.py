from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

try:
    from . import project_paths
except ImportError:  # pragma: no cover - executed when run as a script
    import sys

    module_path = Path(__file__).resolve().parent
    module_dir = str(module_path)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    import project_paths  # type: ignore


DEFINE_RE = re.compile(r"#define\s+(\w+)\s+([^/\n]+)")
ENUM_ENTRY_RE = re.compile(r"^(\s*)([A-Z0-9_]+)\s*(?:=\s*([^,]+))?,?")
SPECIES_NAME_RE = re.compile(r"\[\s*(SPECIES_[A-Z0-9_]+)\s*][^[]+?\.speciesName\s*=\s*_\(\"([^\"]+)\"\)", re.DOTALL)
HEIGHT_RE = re.compile(r"\.height\s*=\s*(\d+)")
WEIGHT_RE = re.compile(r"\.weight\s*=\s*(\d+)")
FAMILY_MACRO_RE = re.compile(r"#define\s+(P_FAMILY_[A-Z0-9_]+)\s+")


@dataclass
class SpeciesMetadata:
    species_constant: str
    display_name: str
    height: Optional[int]
    weight: Optional[int]


def _load_define_constants(path: Path, prefix: str) -> Dict[str, str]:
    constants: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            match = DEFINE_RE.match(line)
            if not match:
                continue
            name, value = match.groups()
            if not name.startswith(prefix):
                continue
            constants[name] = value.strip()
    return constants


def load_species_constants() -> Dict[str, str]:
    return _load_define_constants(project_paths.SPECIES_HEADER_PATH, "SPECIES_")


def load_national_dex_constants() -> Dict[str, str]:
    return _load_define_constants(project_paths.NATIONAL_DEX_HEADER_PATH, "NATIONAL_DEX_")


def load_move_constants() -> Dict[str, str]:
    return _load_define_constants(project_paths.MOVES_HEADER_PATH, "MOVE_")


def load_ability_constants() -> Dict[str, str]:
    return _load_define_constants(project_paths.ABILITIES_HEADER_PATH, "ABILITY_")


def load_item_constants() -> Dict[str, str]:
    return _load_define_constants(project_paths.ITEMS_HEADER_PATH, "ITEM_")


def load_type_constants() -> Dict[str, str]:
    return _load_define_constants(project_paths.TYPES_HEADER_PATH, "TYPE_")


def _load_enum_constants(prefix: str) -> List[str]:
    constants: List[str] = []
    with project_paths.POKEMON_HEADER_PATH.open("r", encoding="utf-8") as handle:
        inside_enum = False
        for raw_line in handle:
            line = raw_line.rstrip()
            if prefix in line:
                inside_enum = True
            if inside_enum:
                match = ENUM_ENTRY_RE.match(line)
                if match:
                    _, name, _ = match.groups()
                    if name.startswith(prefix):
                        constants.append(name)
            if inside_enum and line.startswith("}"):
                inside_enum = False
    return constants


def load_evolution_methods() -> List[str]:
    return _load_enum_constants("EVO_")


def load_growth_rates() -> List[str]:
    return _load_enum_constants("GROWTH_")


def load_egg_groups() -> List[str]:
    return _load_enum_constants("EGG_GROUP_")


def load_family_macros() -> List[str]:
    macros: List[str] = []
    with project_paths.SPECIES_ENABLED_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            match = FAMILY_MACRO_RE.match(line)
            if match:
                macros.append(match.group(1))
    return macros


def load_species_metadata() -> Dict[str, SpeciesMetadata]:
    metadata: Dict[str, SpeciesMetadata] = {}
    for path in project_paths.SPECIES_INFO_DIR.glob("**/*.h"):
        text = path.read_text(encoding="utf-8")
        for match in SPECIES_NAME_RE.finditer(text):
            species, display = match.groups()
            block = text[match.start():]
            # Limit block search to avoid capturing the entire rest of the file.
            end_index = block.find("\n}\n")
            snippet = block[: end_index if end_index != -1 else len(block)]
            height_match = HEIGHT_RE.search(snippet)
            weight_match = WEIGHT_RE.search(snippet)
            metadata[species] = SpeciesMetadata(
                species_constant=species,
                display_name=display,
                height=int(height_match.group(1)) if height_match else None,
                weight=int(weight_match.group(1)) if weight_match else None,
            )
    return metadata


def ensure_constant_exists(constants: Dict[str, str], constant: str) -> None:
    if constant not in constants:
        raise ValueError(f"Unknown constant: {constant}")


def normalize_species_constant(species: str) -> str:
    species = species.strip().upper()
    if not species.startswith("SPECIES_"):
        species = f"SPECIES_{species}"
    return species


def normalize_natdex_constant(natdex: str) -> str:
    natdex = natdex.strip().upper()
    if not natdex.startswith("NATIONAL_DEX_"):
        natdex = f"NATIONAL_DEX_{natdex}"
    return natdex


def showdown_folder_from_species(species: str) -> str:
    """Derive a default graphics folder from a species constant."""
    base = species
    if species.startswith("SPECIES_"):
        base = species[len("SPECIES_") :]
    return base.lower()
