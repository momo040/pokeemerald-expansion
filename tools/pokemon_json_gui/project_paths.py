from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_JSON_ROOT = REPO_ROOT / "data" / "json" / "pokemon"
GRAPHICS_ROOT = REPO_ROOT / "graphics" / "pokemon"
DATABASE_PATH = REPO_ROOT / "build" / "pokemon_json_gui" / "pokemon.db"
SPECIES_ENABLED_PATH = REPO_ROOT / "include" / "config" / "species_enabled.h"
POKEDEX_ORDERS_PATH = REPO_ROOT / "src" / "data" / "pokemon" / "pokedex_orders.h"
CRY_TABLE_PATH = REPO_ROOT / "sound" / "cry_tables.inc"
SPECIES_HEADER_PATH = REPO_ROOT / "include" / "constants" / "species.h"
NATIONAL_DEX_HEADER_PATH = REPO_ROOT / "include" / "constants" / "pokedex.h"
MOVES_HEADER_PATH = REPO_ROOT / "include" / "constants" / "moves.h"
ABILITIES_HEADER_PATH = REPO_ROOT / "include" / "constants" / "abilities.h"
ITEMS_HEADER_PATH = REPO_ROOT / "include" / "constants" / "items.h"
POKEMON_HEADER_PATH = REPO_ROOT / "include" / "constants" / "pokemon.h"

_POKEMON_TYPES_HEADER_DEFAULT = REPO_ROOT / "include" / "constants" / "pokemon_types.h"
if _POKEMON_TYPES_HEADER_DEFAULT.exists():
    TYPES_HEADER_PATH = _POKEMON_TYPES_HEADER_DEFAULT
else:
    TYPES_HEADER_PATH = POKEMON_HEADER_PATH
SPECIES_INFO_DIR = REPO_ROOT / "src" / "data" / "pokemon" / "species_info"


def ensure_directories() -> None:
    DATA_JSON_ROOT.mkdir(parents=True, exist_ok=True)
    GRAPHICS_ROOT.mkdir(parents=True, exist_ok=True)
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
