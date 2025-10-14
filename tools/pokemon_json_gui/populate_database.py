"""Simplified database population for the Pokémon JSON GUI tool.

This utility scans the repository to identify the currently enabled species and
stores lightweight summaries in the GUI's SQLite database.  The script focuses
on providing enough information for browsing and quick reference; detailed
attributes such as learnsets and numeric stats are left empty to avoid the
complexity of parsing the entire game data model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from . import project_paths
    from .constants_loader import (
        SpeciesMetadata,
        load_enabled_family_macros,
        load_species_metadata,
        showdown_folder_from_species,
    )
    from .data_models import PokemonData
    from .database import PokemonDatabase
    from .file_manager import AssetBundle
except ImportError:  # pragma: no cover - executed when run as a script
    import sys

    module_path = Path(__file__).resolve().parent
    module_dir = str(module_path)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    import project_paths  # type: ignore
    from constants_loader import (  # type: ignore
        SpeciesMetadata,
        load_enabled_family_macros,
        load_species_metadata,
        showdown_folder_from_species,
    )
    from data_models import PokemonData  # type: ignore
    from database import PokemonDatabase  # type: ignore
    from file_manager import AssetBundle  # type: ignore


SPECIES_MARKER = "[SPECIES_"


def _species_family_mapping() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for path in sorted(project_paths.SPECIES_INFO_DIR.glob("*.h")):
        current_family: Optional[str] = None
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#if P_FAMILY_"):
                parts = stripped.split()
                if parts:
                    current_family = parts[1]
                continue
            if stripped.startswith("#endif"):
                if "P_FAMILY_" in stripped:
                    current_family = None
                continue
            if stripped.startswith(SPECIES_MARKER) and current_family:
                end = stripped.find("]")
                if end != -1:
                    species_name = stripped[len("[") : end]
                    mapping[species_name] = current_family
    return mapping


def _collect_enabled_species() -> List[str]:
    enabled_families = set(load_enabled_family_macros())
    mapping = _species_family_mapping()
    return [species for species, family in mapping.items() if family in enabled_families]


def _build_asset_bundle(folder: str) -> Optional[AssetBundle]:
    base = project_paths.GRAPHICS_ROOT / folder
    front = base / "front.png"
    back = base / "back.png"
    icon = base / "icon.png"
    normal_pal = base / "normal.pal"
    if not all(path.exists() for path in (front, back, icon, normal_pal)):
        return None
    shiny_pal = base / "shiny.pal"
    return AssetBundle(
        front=front,
        back=back,
        icon=icon,
        normal_palette=normal_pal,
        shiny_palette=shiny_pal if shiny_pal.exists() else None,
        optional_assets={},
        cry_sample=None,
    )


def _create_stub_pokemon(
    species: str,
    metadata: Dict[str, SpeciesMetadata],
) -> Tuple[PokemonData, Optional[AssetBundle]]:
    meta = metadata.get(species)
    display_name = meta.display_name if meta else species
    height = meta.height if meta and meta.height is not None else 0
    weight = meta.weight if meta and meta.weight is not None else 0

    folder = showdown_folder_from_species(species)
    assets = _build_asset_bundle(folder)

    pokemon = PokemonData(
        species_constant=species,
        family_macro=species.replace("SPECIES_", "P_FAMILY_"),
        national_dex_constant=f"NATIONAL_DEX_{species.replace('SPECIES_', '')}",
        display_name=display_name,
        category_name="",
        description="",
        height=height,
        weight=weight,
        types=["TYPE_NORMAL", "TYPE_NORMAL"],
        abilities=["ABILITY_NONE"],
        catch_rate=0,
        exp_yield=0,
        growth_rate="GROWTH_MEDIUM_FAST",
        egg_groups=["EGG_GROUP_NO_EGGS_DISCOVERED", "EGG_GROUP_NO_EGGS_DISCOVERED"],
        gender_ratio="MON_GENDERLESS",
        egg_cycles=0,
        friendship="70",
        base_stats={
            "hp": 0,
            "attack": 0,
            "defense": 0,
            "speed": 0,
            "spAttack": 0,
            "spDefense": 0,
        },
        ev_yield={},
        learnset_level_up=[],
        learnset_egg=[],
        learnset_tm=[],
        evolutions=[],
        dex_order_hint={"height": height, "weight": weight},
        cry="CRY_NONE",
        graphics_folder=folder,
    )
    return pokemon, assets


def populate_database(database: PokemonDatabase) -> None:
    metadata = load_species_metadata()
    species_list = _collect_enabled_species()
    for species in species_list:
        pokemon, assets = _create_stub_pokemon(species, metadata)
        if assets is None:
            continue
        database.save_entry(pokemon, assets)


def main() -> None:
    project_paths.ensure_directories()
    database = PokemonDatabase()
    populate_database(database)


if __name__ == "__main__":
    main()

