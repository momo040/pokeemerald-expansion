from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Mapping, Optional


@dataclass
class LearnsetEntry:
    level: int
    move: str

    def to_dict(self) -> Dict[str, object]:
        return {"level": self.level, "move": self.move}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LearnsetEntry":
        try:
            level = int(payload["level"])
            move = payload["move"]
        except KeyError as exc:  # pragma: no cover - defensive conversion
            raise ValueError(f"Missing learnset entry field: {exc.args[0]}") from exc
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive conversion
            raise ValueError("Invalid learnset entry level") from exc
        if not isinstance(move, str):  # pragma: no cover - defensive conversion
            raise ValueError("Learnset move must be a string")
        return cls(level=level, move=move)


@dataclass
class EvolutionEntry:
    from_species: str
    method: str
    parameter: str
    target_species: str
    conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "from": self.from_species,
            "method": self.method,
            "parameter": self.parameter,
            "to": self.target_species,
            "conditions": list(self.conditions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "EvolutionEntry":
        try:
            from_species = payload["from"]
            method = payload["method"]
            parameter = payload["parameter"]
            target_species = payload["to"]
        except KeyError as exc:  # pragma: no cover - defensive conversion
            raise ValueError(f"Missing evolution field: {exc.args[0]}") from exc
        conditions = payload.get("conditions", [])
        if not isinstance(conditions, list):  # pragma: no cover - defensive conversion
            raise ValueError("Evolution conditions must be a list")
        return cls(
            from_species=str(from_species),
            method=str(method),
            parameter=str(parameter),
            target_species=str(target_species),
            conditions=[str(condition) for condition in conditions],
        )


@dataclass
class PokemonData:
    species_constant: str
    family_macro: str
    national_dex_constant: str
    display_name: str
    category_name: str
    description: str
    height: int
    weight: int
    types: List[str]
    abilities: List[str]
    catch_rate: int
    exp_yield: int
    growth_rate: str
    egg_groups: List[str]
    gender_ratio: str
    egg_cycles: int
    friendship: str
    base_stats: Dict[str, int]
    ev_yield: Dict[str, int]
    learnset_level_up: List[LearnsetEntry]
    learnset_egg: List[str]
    learnset_tm: List[str]
    evolutions: List[EvolutionEntry]
    dex_order_hint: Dict[str, int]
    cry: str
    graphics_folder: str
    icon_pal_index: Optional[int] = None
    extra_graphics: Dict[str, str] = field(default_factory=dict)

    def base_stats_json(self) -> Dict[str, object]:
        payload = {
            "species": self.species_constant,
            "types": list(self.types),
            "abilities": list(self.abilities),
            "catchRate": self.catch_rate,
            "expYield": self.exp_yield,
            "growthRate": self.growth_rate,
            "eggGroups": list(self.egg_groups),
            "genderRatio": self.gender_ratio,
            "eggCycles": self.egg_cycles,
            "friendship": self.friendship,
            "baseStats": dict(self.base_stats),
            "evYield": dict(self.ev_yield),
        }
        if self.icon_pal_index is not None:
            payload["iconPalIndex"] = self.icon_pal_index
        return payload

    def learnsets_json(self) -> Dict[str, object]:
        return {
            "levelUp": [entry.to_dict() for entry in self.learnset_level_up],
            "egg": list(self.learnset_egg),
            "tm": list(self.learnset_tm),
        }

    def evolutions_json(self) -> Dict[str, object]:
        return {
            "entries": [entry.to_dict() for entry in self.evolutions],
        }

    def pokedex_json(self) -> Dict[str, object]:
        return {
            "species": self.species_constant,
            "name": self.display_name,
            "category": self.category_name,
            "description": self.description,
            "height": self.height,
            "weight": self.weight,
            "cry": self.cry,
            "nationalDex": self.national_dex_constant,
        }

    def names_json(self) -> Dict[str, object]:
        return {
            "species": self.species_constant,
            "name": self.display_name,
            "category": self.category_name,
        }

    def dex_order_json(self) -> Dict[str, object]:
        return dict(self.dex_order_hint)

    def to_summary(self) -> Dict[str, object]:
        summary = asdict(self)
        summary["learnset_level_up"] = [entry.to_dict() for entry in self.learnset_level_up]
        summary["evolutions"] = [entry.to_dict() for entry in self.evolutions]
        return summary

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "PokemonData":
        def require(field: str) -> Any:
            if field not in payload:
                raise ValueError(f"Missing Pokémon field: {field}")
            return payload[field]

        learnset_level_payload = payload.get("learnset_level_up", [])
        learnset_level = [
            LearnsetEntry.from_dict(entry) for entry in learnset_level_payload
        ]
        evolutions_payload = payload.get("evolutions", [])
        evolutions = [
            EvolutionEntry.from_dict(entry) for entry in evolutions_payload
        ]

        try:
            height = int(require("height"))
            weight = int(require("weight"))
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive conversion
            raise ValueError("Height and weight must be integers") from exc

        dex_hint = payload.get("dex_order_hint")
        if dex_hint is None:
            dex_hint = {"height": height, "weight": weight}

        icon_pal_index = payload.get("icon_pal_index")
        if icon_pal_index is not None:
            try:
                icon_pal_index = int(icon_pal_index)
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive conversion
                raise ValueError("icon_pal_index must be an integer") from exc

        return cls(
            species_constant=str(require("species_constant")),
            family_macro=str(require("family_macro")),
            national_dex_constant=str(require("national_dex_constant")),
            display_name=str(require("display_name")),
            category_name=str(require("category_name")),
            description=str(require("description")),
            height=height,
            weight=weight,
            types=[str(value) for value in payload.get("types", [])],
            abilities=[str(value) for value in payload.get("abilities", [])],
            catch_rate=int(require("catch_rate")),
            exp_yield=int(require("exp_yield")),
            growth_rate=str(require("growth_rate")),
            egg_groups=[str(value) for value in payload.get("egg_groups", [])],
            gender_ratio=str(require("gender_ratio")),
            egg_cycles=int(require("egg_cycles")),
            friendship=str(require("friendship")),
            base_stats={str(key): int(value) for key, value in require("base_stats").items()},
            ev_yield={str(key): int(value) for key, value in require("ev_yield").items()},
            learnset_level_up=learnset_level,
            learnset_egg=[str(value) for value in payload.get("learnset_egg", [])],
            learnset_tm=[str(value) for value in payload.get("learnset_tm", [])],
            evolutions=evolutions,
            dex_order_hint={str(k): int(v) for k, v in dex_hint.items()},
            cry=str(require("cry")),
            graphics_folder=str(require("graphics_folder")),
            icon_pal_index=icon_pal_index,
            extra_graphics={str(k): str(v) for k, v in payload.get("extra_graphics", {}).items()},
        )
