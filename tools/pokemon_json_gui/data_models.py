from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class LearnsetEntry:
    level: int
    move: str

    def to_dict(self) -> Dict[str, object]:
        return {"level": self.level, "move": self.move}


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
