from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    from . import project_paths
    from .constants_loader import (
        SpeciesMetadata,
        load_species_metadata,
        showdown_folder_from_species,
    )
    from .data_models import PokemonData
    from .image_utils import ensure_shiny_palette, validate_palette, validate_png
except ImportError:  # pragma: no cover - executed when run as a script
    import sys

    module_path = Path(__file__).resolve().parent
    module_dir = str(module_path)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    import project_paths  # type: ignore
    from constants_loader import (  # type: ignore
        SpeciesMetadata,
        load_species_metadata,
        showdown_folder_from_species,
    )
    from data_models import PokemonData  # type: ignore
    from image_utils import ensure_shiny_palette, validate_palette, validate_png  # type: ignore

OPTIONAL_SIZE_HINTS = {
    "anim_front.png": (64, 64),
    "anim_front_hd.png": (64, 64),
    "anim_back.png": (64, 64),
    "footprint.png": (16, 16),
}


@dataclass
class AssetBundle:
    front: Path
    back: Path
    icon: Path
    normal_palette: Path
    shiny_palette: Optional[Path]
    optional_assets: Dict[str, Path]
    cry_sample: Optional[Path]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AssetBundle":
        def require_path(key: str) -> Path:
            try:
                value = payload[key]
            except KeyError as exc:  # pragma: no cover - defensive conversion
                raise ValueError(f"Missing asset path: {key}") from exc
            if not isinstance(value, str):  # pragma: no cover - defensive conversion
                raise ValueError(f"Asset path for {key} must be a string")
            stripped = value.strip()
            if not stripped:
                raise ValueError(f"Asset path for {key} is empty")
            return Path(stripped)

        optional_raw = payload.get("optional_assets", {})
        if not isinstance(optional_raw, Mapping):  # pragma: no cover - defensive conversion
            raise ValueError("optional_assets must be a mapping")
        optional_assets = {}
        for name, raw_path in optional_raw.items():
            path_str = str(raw_path).strip()
            if not path_str:
                continue
            optional_assets[str(name)] = Path(path_str)

        shiny = payload.get("shiny_palette")
        cry = payload.get("cry_sample")

        shiny_value = str(shiny).strip() if shiny is not None else ""
        cry_value = str(cry).strip() if cry is not None else ""

        shiny_path = Path(shiny_value) if shiny_value else None
        cry_path = Path(cry_value) if cry_value else None

        return cls(
            front=require_path("front"),
            back=require_path("back"),
            icon=require_path("icon"),
            normal_palette=require_path("normal_palette"),
            shiny_palette=shiny_path,
            optional_assets=optional_assets,
            cry_sample=cry_path,
        )

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "front": str(self.front),
            "back": str(self.back),
            "icon": str(self.icon),
            "normal_palette": str(self.normal_palette),
            "optional_assets": {name: str(path) for name, path in self.optional_assets.items()},
        }
        if self.shiny_palette is not None:
            payload["shiny_palette"] = str(self.shiny_palette)
        if self.cry_sample is not None:
            payload["cry_sample"] = str(self.cry_sample)
        return payload


ARRAY_RE_TEMPLATE = r"const u16 {name}\[\] =\s*\{{\n(?P<body>.*?)\n\}};"
FAMILY_BLOCK_TEMPLATE = r"\.if\s+{macro}\s*==\s*TRUE\s*\n(?P<body>.*?)\n\.endif @ {macro}"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def copy_asset(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def apply_graphics(pokemon: PokemonData, assets: AssetBundle) -> None:
    graphics_folder = project_paths.GRAPHICS_ROOT / pokemon.graphics_folder
    graphics_folder.mkdir(parents=True, exist_ok=True)

    validate_png(assets.front, (64, 64))
    validate_png(assets.back, (64, 64))
    validate_png(assets.icon, (32, 32))

    copy_asset(assets.front, graphics_folder / "front.png")
    copy_asset(assets.back, graphics_folder / "back.png")
    copy_asset(assets.icon, graphics_folder / "icon.png")

    validate_palette(assets.normal_palette)
    normal_dest = graphics_folder / "normal.pal"
    copy_asset(assets.normal_palette, normal_dest)
    shiny_dest = graphics_folder / "shiny.pal"
    if assets.shiny_palette:
        validate_palette(assets.shiny_palette)
        copy_asset(assets.shiny_palette, shiny_dest)
    else:
        ensure_shiny_palette(normal_dest, shiny_dest)

    for target_name, value in assets.optional_assets.items():
        destination = graphics_folder / target_name
        hint = OPTIONAL_SIZE_HINTS.get(target_name)
        if hint and value.suffix.lower() == ".png":
            validate_png(value, hint)
        copy_asset(value, destination)


def save_json_payloads(pokemon: PokemonData) -> None:
    species_folder = project_paths.DATA_JSON_ROOT / pokemon.graphics_folder
    write_json(species_folder / "base_stats.json", pokemon.base_stats_json())
    learnsets = pokemon.learnsets_json()
    write_json(species_folder / "learnsets" / "level_up.json", {"entries": learnsets["levelUp"]})
    write_json(species_folder / "learnsets" / "egg.json", {"moves": learnsets["egg"]})
    write_json(species_folder / "learnsets" / "tm.json", {"moves": learnsets["tm"]})
    write_json(species_folder / "evolutions.json", pokemon.evolutions_json())
    write_json(species_folder / "pokedex.json", pokemon.pokedex_json())
    write_json(species_folder / "names.json", pokemon.names_json())
    write_json(species_folder / "dex_order.json", pokemon.dex_order_json())


def update_family_toggle(family_macro: str) -> bool:
    text = project_paths.SPECIES_ENABLED_PATH.read_text(encoding="utf-8")
    pattern = rf"(#define\s+{family_macro}\s+)([^/\n]+)"
    match = re.search(pattern, text)
    if not match:
        raise ValueError(f"Could not find {family_macro} in {project_paths.SPECIES_ENABLED_PATH}")
    current = match.group(2).strip()
    if current == "TRUE":
        return False
    suffix = text[match.end(2):match.end()]
    text = text[: match.start()] + match.group(1) + "TRUE" + suffix + text[match.end():]
    project_paths.SPECIES_ENABLED_PATH.write_text(text, encoding="utf-8")
    return True


def parse_array(path: Path, array_name: str) -> List[str]:
    pattern = re.compile(ARRAY_RE_TEMPLATE.format(name=array_name), re.DOTALL)
    text = path.read_text(encoding="utf-8")
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Unable to locate array {array_name} in {path}")
    body = match.group("body")
    return [line.strip().rstrip(",") for line in body.splitlines() if line.strip()]


def format_array(entries: Sequence[str]) -> str:
    return "\n".join(f"    {entry}," for entry in entries)


def update_array(path: Path, array_name: str, new_entries: Sequence[str]) -> None:
    import re

    text = path.read_text(encoding="utf-8")
    pattern = re.compile(ARRAY_RE_TEMPLATE.format(name=array_name), re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Unable to locate array {array_name} in {path}")
    new_body = format_array(new_entries)
    text = text[: match.start("body")] + new_body + text[match.end("body") :]
    path.write_text(text, encoding="utf-8")


def update_pokedex_orders(pokemon: PokemonData) -> None:
    import re

    metadata = load_species_metadata()
    metadata[pokemon.species_constant] = SpeciesMetadata(
        species_constant=pokemon.species_constant,
        display_name=pokemon.display_name,
        height=pokemon.height,
        weight=pokemon.weight,
    )

    path = project_paths.POKEDEX_ORDERS_PATH
    def species_from_natdex(natdex: str) -> str:
        return natdex.replace("NATIONAL_DEX_", "SPECIES_")

    def alphabetical_key(entry: str) -> Tuple[str, str]:
        species_key = species_from_natdex(entry)
        meta = metadata.get(species_key)
        name = meta.display_name.lower() if meta else entry.lower()
        return name, entry

    def numeric_key(entry: str, attribute: str) -> Tuple[int, str]:
        species_key = species_from_natdex(entry)
        meta = metadata.get(species_key)
        value = getattr(meta, attribute) if meta else None
        return (value if value is not None else 10 ** 6, entry)

    arrays = {
        "gPokedexOrder_Alphabetical": lambda entry: alphabetical_key(entry),
        "gPokedexOrder_Height": lambda entry: numeric_key(entry, "height"),
        "gPokedexOrder_Weight": lambda entry: numeric_key(entry, "weight"),
    }

    for array_name, key_fn in arrays.items():
        entries = parse_array(path, array_name)
        target = pokemon.national_dex_constant
        if target not in entries:
            entries.append(target)
        entries = sorted(set(entries), key=key_fn)
        update_array(path, array_name, entries)


def insert_cry_line(text: str, start_marker: str, family_macro: str, directive: str, cry_label: str) -> Tuple[str, bool]:
    import re

    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError(f"Could not locate {start_marker} in cry table")
    if start_marker == "gCryTable::":
        end_marker = "gCryTable_Reverse::"
        end_index = text.find(end_marker, start_index + len(start_marker))
        if end_index == -1:
            end_index = len(text)
    else:
        end_index = len(text)
    section = text[start_index:end_index]
    block_pattern = re.compile(
        FAMILY_BLOCK_TEMPLATE.format(macro=family_macro), re.DOTALL
    )
    match = block_pattern.search(section)
    if not match:
        raise ValueError(f"Unable to find block for {family_macro} in cry table section")
    body = match.group("body")
    line = f"        {directive} {cry_label}"
    if line in body:
        return text, False
    newline = "\n" if not body.endswith("\n") else ""
    body_with_entry = body + newline + line + "\n"
    new_section = section[: match.start("body")] + body_with_entry + section[match.end("body") :]
    text = text[:start_index] + new_section + text[end_index:]
    return text, True


def update_cry_tables(family_macro: str, cry_label: str) -> bool:
    text = project_paths.CRY_TABLE_PATH.read_text(encoding="utf-8")
    updated = False
    text, changed_forward = insert_cry_line(text, "gCryTable::", family_macro, "cry", cry_label)
    updated = updated or changed_forward
    text, changed_reverse = insert_cry_line(text, "gCryTable_Reverse::", family_macro, "cry_reverse", cry_label)
    updated = updated or changed_reverse
    if updated:
        project_paths.CRY_TABLE_PATH.write_text(text, encoding="utf-8")
    return updated


def copy_cry_sample(sample: Optional[Path], cry_label: str) -> Optional[Path]:
    if not sample:
        return None
    target_dir = project_paths.REPO_ROOT / "sound" / "direct_sound_samples" / "cries"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_name = cry_label.replace("Cry_", "").lower() + ".aif"
    target = target_dir / file_name
    copy_asset(sample, target)
    return target
