from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

try:
    from . import project_paths
    from .data_models import PokemonData
    from .file_manager import AssetBundle
except ImportError:  # pragma: no cover - executed when run as a script
    import sys

    module_path = Path(__file__).resolve().parent
    module_dir = str(module_path)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)

    import project_paths  # type: ignore
    from data_models import PokemonData  # type: ignore
    from file_manager import AssetBundle  # type: ignore


@dataclass
class PokemonRecord:
    species_constant: str
    display_name: str
    updated_at: str
    family_macro: Optional[str] = None


class PokemonDatabase:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else project_paths.DATABASE_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    # ------------------------------------------------------------------
    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pokemon (
                    species_constant TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    assets TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )

    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    def save_entry(self, pokemon: PokemonData, assets: AssetBundle) -> None:
        payload = json.dumps(pokemon.to_summary())
        asset_payload = json.dumps(assets.to_dict())
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pokemon (species_constant, display_name, payload, assets, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(species_constant) DO UPDATE SET
                    display_name=excluded.display_name,
                    payload=excluded.payload,
                    assets=excluded.assets,
                    updated_at=datetime('now')
                """,
                (pokemon.species_constant, pokemon.display_name, payload, asset_payload),
            )

    # ------------------------------------------------------------------
    def list_entries(
        self,
        *,
        enabled_families: Optional[Iterable[str]] = None,
        valid_species: Optional[Set[str]] = None,
    ) -> List[PokemonRecord]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT species_constant, display_name, payload, updated_at
                FROM pokemon
                ORDER BY updated_at DESC, species_constant ASC
                """
            )
            records: List[PokemonRecord] = []
            enabled_set = set(enabled_families) if enabled_families is not None else None
            for row in cursor.fetchall():
                species_constant = row["species_constant"]
                if valid_species is not None and species_constant not in valid_species:
                    continue

                family_macro: Optional[str] = None
                payload_text = row["payload"]
                if payload_text:
                    try:
                        payload = json.loads(payload_text)
                    except (TypeError, json.JSONDecodeError):  # pragma: no cover - defensive parsing
                        payload = {}
                    family_value = payload.get("family_macro")
                    if isinstance(family_value, str) and family_value:
                        family_macro = family_value.strip()

                if enabled_set is not None and (not family_macro or family_macro not in enabled_set):
                    continue

                records.append(
                    PokemonRecord(
                        species_constant=species_constant,
                        display_name=row["display_name"],
                        updated_at=row["updated_at"],
                        family_macro=family_macro,
                    )
                )
            return records

    # ------------------------------------------------------------------
    def load_entry(self, species_constant: str) -> Tuple[PokemonData, AssetBundle]:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT payload, assets FROM pokemon WHERE species_constant = ?",
                (species_constant,),
            )
            row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Species {species_constant} not found in database")

        pokemon_payload = json.loads(row["payload"])
        assets_payload = json.loads(row["assets"])
        return PokemonData.from_dict(pokemon_payload), AssetBundle.from_dict(assets_payload)
