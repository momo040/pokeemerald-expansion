from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if __package__:
    from . import project_paths
    from .audio_utils import load_available_cries
    from .constants_loader import (
        ensure_constant_exists,
        load_ability_constants,
        load_egg_groups,
        load_evolution_methods,
        load_enabled_family_macros,
        load_family_macros,
        load_growth_rates,
        load_move_constants,
        load_national_dex_constants,
        load_species_constants,
        load_species_metadata,
        load_type_constants,
        normalize_natdex_constant,
        normalize_species_constant,
        showdown_folder_from_species,
        load_species_family_mapping,
    )
    from .data_models import EvolutionEntry, LearnsetEntry, PokemonData
    from .database import PokemonDatabase, PokemonRecord
    from .file_manager import (
        AssetBundle,
        apply_graphics,
        copy_cry_sample,
        save_json_payloads,
        update_cry_tables,
        update_family_toggle,
        update_pokedex_orders,
    )
    from .image_utils import PillowUnavailableError
else:  # pragma: no cover - executed when run as a script
    import os
    import sys

    module_path = os.path.dirname(os.path.abspath(__file__))
    if module_path not in sys.path:
        sys.path.insert(0, module_path)

    import project_paths  # type: ignore
    from audio_utils import load_available_cries  # type: ignore
    from constants_loader import (  # type: ignore
        ensure_constant_exists,
        load_ability_constants,
        load_egg_groups,
        load_evolution_methods,
        load_enabled_family_macros,
        load_family_macros,
        load_growth_rates,
        load_move_constants,
        load_national_dex_constants,
        load_species_constants,
        load_species_metadata,
        load_type_constants,
        normalize_natdex_constant,
        normalize_species_constant,
        showdown_folder_from_species,
        load_species_family_mapping,
    )
    from data_models import EvolutionEntry, LearnsetEntry, PokemonData  # type: ignore
    from database import PokemonDatabase, PokemonRecord  # type: ignore
    from file_manager import (  # type: ignore
        AssetBundle,
        apply_graphics,
        copy_cry_sample,
        save_json_payloads,
        update_cry_tables,
        update_family_toggle,
        update_pokedex_orders,
    )
    from image_utils import PillowUnavailableError  # type: ignore


REQUIRED_ASSETS = {
    "Front Sprite": ("front", ("PNG files", "*.png")),
    "Back Sprite": ("back", ("PNG files", "*.png")),
    "Icon": ("icon", ("PNG files", "*.png")),
    "Normal Palette": ("normal_palette", ("Palette files", "*.pal")),
}

OPTIONAL_ASSETS = {
    "Shiny Palette": ("shiny_palette", ("Palette files", "*.pal")),
    "Front Animation": ("anim_front.png", ("PNG files", "*.png")),
    "Back Animation": ("anim_back.png", ("PNG files", "*.png")),
    "Footprint": ("footprint.png", ("PNG files", "*.png")),
    "Cry Sample (.aif)": ("cry_sample", ("AIFF", "*.aif")),
}


def generate_pokemon_assets(
    data: PokemonData,
    assets: AssetBundle,
    logger: Optional[Callable[[str], None]] = None,
) -> None:
    def log(message: str) -> None:
        if logger:
            logger(message)

    project_paths.ensure_directories()
    log("Enabling family macro…")
    update_family_toggle(data.family_macro)
    log("Copying graphics and validating sprites…")
    apply_graphics(data, assets)
    log("Writing JSON payloads…")
    save_json_payloads(data)
    log("Updating dex order tables…")
    update_pokedex_orders(data)
    log("Refreshing cry tables…")
    update_cry_tables(data.family_macro, data.cry)
    if assets.cry_sample:
        log("Copying cry sample…")
        copy_cry_sample(assets.cry_sample, data.cry)
    log("Generation complete.")


def run_headless(
    config_path: Path,
    summary_output: Optional[Path],
    database_path: Optional[Path],
    store_in_database: bool,
) -> None:
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    pokemon_payload = payload.get("pokemon")
    if pokemon_payload is None:
        raise ValueError("Configuration must include a 'pokemon' section.")
    assets_payload = payload.get("assets")
    if assets_payload is None:
        raise ValueError("Configuration must include an 'assets' section.")

    pokemon = PokemonData.from_dict(pokemon_payload)
    assets = AssetBundle.from_dict(assets_payload)

    summary_path = summary_output
    if summary_path is None:
        summary_raw = payload.get("summary_output")
        if summary_raw:
            summary_path = Path(str(summary_raw))

    generate_pokemon_assets(pokemon, assets, logger=lambda message: print(message, flush=True))

    if store_in_database:
        database = PokemonDatabase(database_path)
        database.save_entry(pokemon, assets)
        print(f"Stored {pokemon.species_constant} in database.", flush=True)

    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_content = json.dumps(pokemon.to_summary(), indent=2)
        summary_path.write_text(summary_content + "\n", encoding="utf-8")


@dataclass
class LearnsetState:
    entries: List[LearnsetEntry]

    def add(self, entry: LearnsetEntry) -> None:
        self.entries.append(entry)
        self.entries.sort(key=lambda value: (value.level, value.move))

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.entries):
            self.entries.pop(index)

    def as_display(self) -> List[str]:
        return [f"Lv {entry.level}: {entry.move}" for entry in self.entries]


class DatabaseBrowser(tk.Toplevel):
    def __init__(
        self,
        master: tk.Widget,
        database: PokemonDatabase,
        load_callback: Callable[[str], None],
        apply_callback: Callable[[str], None],
    ) -> None:
        super().__init__(master)
        self.database = database
        self.load_callback = load_callback
        self.apply_callback = apply_callback
        self.title("Stored Pokémon")
        self.geometry("560x380")
        self.transient(master)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._record_sources: Dict[str, str] = {}

        columns = ("species", "display", "updated")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("species", text="Species")
        self.tree.heading("display", text="Display Name")
        self.tree.heading("updated", text="Updated")
        self.tree.column("species", width=160, anchor="w")
        self.tree.column("display", width=200, anchor="w")
        self.tree.column("updated", width=160, anchor="w")
        self.tree.grid(row=0, column=0, columnspan=4, sticky="nsew")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=4, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<Double-1>", self._on_double_click)

        button_frame = ttk.Frame(self, padding=(0, 8, 0, 0))
        button_frame.grid(row=1, column=0, columnspan=5, sticky="ew")
        button_frame.columnconfigure(0, weight=1)
        ttk.Button(button_frame, text="Refresh", command=self.refresh).grid(row=0, column=0, sticky="w")
        self.load_button = ttk.Button(button_frame, text="Load into Form", command=self._load_selected)
        self.load_button.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.apply_button = ttk.Button(button_frame, text="Apply to Project", command=self._apply_selected)
        self.apply_button.grid(row=0, column=2, sticky="e", padx=(8, 0))
        ttk.Button(button_frame, text="Close", command=self.destroy).grid(row=0, column=3, sticky="e", padx=(8, 0))

        self.grab_set()
        self.tree.bind("<<TreeviewSelect>>", self._update_button_states)
        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        self._record_sources.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        enabled_families = set(load_enabled_family_macros())
        valid_species = set(load_species_constants().keys())
        records = self.database.list_entries(
            enabled_families=enabled_families,
            valid_species=valid_species,
        )
        for record in records:
            self.tree.insert(
                "",
                tk.END,
                values=(record.species_constant, record.display_name, record.updated_at),
            )
            self._record_sources[record.species_constant] = "database"

        project_records = self._project_records(enabled_families, valid_species)
        for record in project_records:
            if record.species_constant in self._record_sources:
                continue
            self.tree.insert(
                "",
                tk.END,
                values=(record.species_constant, record.display_name, record.updated_at),
            )
            self._record_sources[record.species_constant] = "project"
        if records:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
        elif project_records:
            first = self.tree.get_children()[0]
            self.tree.selection_set(first)
        self._update_button_states()

    # ------------------------------------------------------------------
    def _project_records(
        self,
        enabled_families: Set[str],
        valid_species: Set[str],
    ) -> List[PokemonRecord]:
        metadata = load_species_metadata()
        family_mapping = load_species_family_mapping()
        records: List[PokemonRecord] = []
        for species, family in family_mapping.items():
            if species not in valid_species:
                continue
            if family not in enabled_families:
                continue
            meta = metadata.get(species)
            display = meta.display_name if meta else species
            records.append(
                PokemonRecord(
                    species_constant=species,
                    display_name=display,
                    updated_at="Project Files",
                    family_macro=family,
                )
            )
        records.sort(key=lambda record: (record.display_name, record.species_constant))
        return records

    # ------------------------------------------------------------------
    def _selected_species(self) -> Optional[str]:
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], "values")
        return values[0] if values else None

    # ------------------------------------------------------------------
    def _update_button_states(self, _event: Optional[tk.Event] = None) -> None:
        species = self._selected_species()
        is_database_entry = species is not None and self._record_sources.get(species) == "database"
        if is_database_entry:
            self.load_button.state(["!disabled"])
            self.apply_button.state(["!disabled"])
        else:
            self.load_button.state(["disabled"])
            self.apply_button.state(["disabled"])

    # ------------------------------------------------------------------
    def _load_selected(self) -> None:
        species = self._selected_species()
        if not species:
            messagebox.showwarning("Database", "Select a Pokémon entry first.")
            return
        if self._record_sources.get(species) != "database":
            messagebox.showinfo(
                "Project entry",
                "This Pokémon is already part of the project files and does not have a saved database entry.",
            )
            return
        try:
            self.load_callback(species)
            self.destroy()
        except Exception as error:  # pragma: no cover - defensive UI handling
            messagebox.showerror("Load failed", str(error))

    # ------------------------------------------------------------------
    def _apply_selected(self) -> None:
        species = self._selected_species()
        if not species:
            messagebox.showwarning("Database", "Select a Pokémon entry first.")
            return
        if self._record_sources.get(species) != "database":
            messagebox.showinfo(
                "Project entry",
                "This Pokémon is already part of the project files and does not have a saved database entry.",
            )
            return
        try:
            self.apply_callback(species)
        except Exception as error:  # pragma: no cover - defensive UI handling
            messagebox.showerror("Apply failed", str(error))

    # ------------------------------------------------------------------
    def _on_double_click(self, _event=None) -> None:
        self._load_selected()


class PokemonApp(tk.Tk):
    def __init__(self, database_path: Optional[Path] = None) -> None:
        super().__init__()
        self.title("Pokémon JSON Generator")
        self.minsize(1024, 720)
        project_paths.ensure_directories()
        self._database_error: Optional[Exception] = None
        try:
            self.database = PokemonDatabase(database_path)
        except Exception as error:  # pragma: no cover - defensive initialization
            self.database = None
            self._database_error = error
        self._database_browser: Optional["DatabaseBrowser"] = None
        self._load_constants()
        self._build_ui()
        if self.database is None and self._database_error is not None:
            self.after(
                200,
                lambda: messagebox.showwarning(
                    "Database unavailable",
                    f"Unable to initialize Pokémon database: {self._database_error}",
                ),
            )

    # ------------------------------------------------------------------
    # constant loading
    # ------------------------------------------------------------------
    def _load_constants(self) -> None:
        self.species_constants = load_species_constants()
        self.natdex_constants = load_national_dex_constants()
        self.move_constants = sorted(load_move_constants().keys())
        self.ability_constants = sorted(load_ability_constants().keys())
        self.type_constants = sorted(load_type_constants().keys())
        self.growth_rates = sorted(load_growth_rates())
        self.egg_groups = sorted(load_egg_groups())
        self.family_macros = sorted(load_family_macros())
        self.evolution_methods = sorted(load_evolution_methods())
        self.cries = load_available_cries()
        self.species_metadata = load_species_metadata()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")

        self._build_species_tab(notebook)
        self._build_stats_tab(notebook)
        self._build_learnsets_tab(notebook)
        self._build_evolutions_tab(notebook)
        self._build_assets_tab(notebook)
        self._build_summary_tab(notebook)

        footer = ttk.Frame(self)
        footer.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        footer.columnconfigure(2, weight=1)
        self.save_button = ttk.Button(footer, text="Save to Database", command=self.save_to_database)
        self.save_button.grid(row=0, column=0, sticky="w")
        self.database_button = ttk.Button(footer, text="Open Database…", command=self.open_database_browser)
        self.database_button.grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.generate_button = ttk.Button(footer, text="Generate JSON and Assets", command=self.generate)
        self.generate_button.grid(row=0, column=2, sticky="e")
        if self.database is None:
            self.save_button.state(["disabled"])
            self.database_button.state(["disabled"])

    # ------------------------------------------------------------------
    def _populate_from_pokemon(self, data: PokemonData) -> None:
        self.species_var.set(data.species_constant)
        self.natdex_var.set(data.national_dex_constant)
        self.family_macro_var.set(data.family_macro)
        self.display_name_var.set(data.display_name)
        self.category_var.set(data.category_name)
        self.cry_var.set(data.cry)

        for stat, var in self.base_stat_vars.items():
            var.set(str(data.base_stats.get(stat, 0)))
        for stat, var in self.ev_vars.items():
            var.set(str(data.ev_yield.get(stat, 0)))

        types = list(data.types)
        self.type1_var.set(types[0] if types else "")
        self.type2_var.set(types[1] if len(types) > 1 else (types[0] if len(types) == 1 and types[0] == "TYPE_NONE" else "TYPE_NONE"))

        abilities = list(data.abilities)
        self.ability1_var.set(abilities[0] if abilities else "ABILITY_NONE")
        self.ability2_var.set(abilities[1] if len(abilities) > 1 else "ABILITY_NONE")
        self.ability3_var.set(abilities[2] if len(abilities) > 2 else "ABILITY_NONE")

        egg_groups = list(data.egg_groups)
        self.egg_group1_var.set(egg_groups[0] if egg_groups else "EGG_GROUP_NONE")
        self.egg_group2_var.set(egg_groups[1] if len(egg_groups) > 1 else "EGG_GROUP_NONE")

        self.catch_rate_var.set(str(data.catch_rate))
        self.exp_yield_var.set(str(data.exp_yield))
        self.growth_var.set(data.growth_rate)
        self.gender_ratio_var.set(data.gender_ratio)
        self.egg_cycles_var.set(str(data.egg_cycles))
        self.friendship_var.set(data.friendship)
        self.icon_palette_var.set(str(data.icon_pal_index) if data.icon_pal_index is not None else "")

        self.level_moves_state.entries = [LearnsetEntry(entry.level, entry.move) for entry in data.learnset_level_up]
        self._refresh_level_moves()
        self.egg_moves = sorted(data.learnset_egg)
        self._refresh_egg_moves()
        self.tm_moves = sorted(data.learnset_tm)
        self._refresh_tm_moves()
        self.evolutions = [
            EvolutionEntry(
                from_species=entry.from_species,
                method=entry.method,
                parameter=entry.parameter,
                target_species=entry.target_species,
                conditions=list(entry.conditions),
            )
            for entry in data.evolutions
        ]
        self._refresh_evolutions()

        self.height_var.set(str(data.height))
        self.weight_var.set(str(data.weight))
        self.graphics_folder_var.set(data.graphics_folder)
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert(tk.END, data.description)

    # ------------------------------------------------------------------
    def _populate_assets(self, assets: AssetBundle) -> None:
        self.asset_vars.setdefault("front", tk.StringVar())
        self.asset_vars.setdefault("back", tk.StringVar())
        self.asset_vars.setdefault("icon", tk.StringVar())
        self.asset_vars.setdefault("normal_palette", tk.StringVar())
        self.asset_vars["front"].set(str(assets.front))
        self.asset_vars["back"].set(str(assets.back))
        self.asset_vars["icon"].set(str(assets.icon))
        self.asset_vars["normal_palette"].set(str(assets.normal_palette))
        for _label, (key, _) in OPTIONAL_ASSETS.items():
            var = self.asset_vars.setdefault(key, tk.StringVar())
            if key == "shiny_palette":
                var.set(str(assets.shiny_palette) if assets.shiny_palette else "")
            elif key == "cry_sample":
                var.set(str(assets.cry_sample) if assets.cry_sample else "")
            else:
                path = assets.optional_assets.get(key)
                var.set(str(path) if path else "")

    # ------------------------------------------------------------------
    def save_to_database(self) -> None:
        if self.database is None:
            messagebox.showerror("Database unavailable", "The Pokémon database could not be initialized.")
            return
        try:
            data = self._collect_data()
            assets = self._build_asset_bundle()
            self.database.save_entry(data, assets)
            self.log(f"Saved {data.species_constant} to database.")
            messagebox.showinfo("Database", f"{data.display_name} stored successfully.")
        except PillowUnavailableError as error:
            messagebox.showerror("Pillow missing", str(error))
        except Exception as error:  # pragma: no cover - defensive UI handling
            traceback.print_exc()
            messagebox.showerror("Save failed", str(error))
            self.log(f"Error: {error}")

    # ------------------------------------------------------------------
    def open_database_browser(self) -> None:
        if self.database is None:
            messagebox.showerror("Database unavailable", "The Pokémon database could not be initialized.")
            return
        if self._database_browser and tk.Toplevel.winfo_exists(self._database_browser):
            self._database_browser.lift()
            return
        browser = DatabaseBrowser(
            self,
            self.database,
            load_callback=self._handle_database_load,
            apply_callback=self._handle_database_apply,
        )
        browser.bind("<Destroy>", lambda _event: setattr(self, "_database_browser", None))
        self._database_browser = browser

    # ------------------------------------------------------------------
    def _handle_database_load(self, species: str) -> None:
        pokemon, assets = self._load_pokemon_from_database(species)
        self._populate_from_pokemon(pokemon)
        self._populate_assets(assets)
        self.log(f"Loaded {species} from database.")
        messagebox.showinfo("Database", f"{pokemon.display_name} loaded into the editor.")

    # ------------------------------------------------------------------
    def _handle_database_apply(self, species: str) -> None:
        pokemon, assets = self._load_pokemon_from_database(species)
        self.log(f"Applying {species} from database…")
        try:
            generate_pokemon_assets(pokemon, assets, logger=self.log)
        except Exception as error:
            self.log(f"Error applying {species}: {error}")
            raise
        messagebox.showinfo("Database", f"{pokemon.display_name} applied to the project.")

    # ------------------------------------------------------------------
    def _load_pokemon_from_database(self, species: str) -> Tuple[PokemonData, AssetBundle]:
        if self.database is None:
            raise RuntimeError("Database unavailable")
        try:
            return self.database.load_entry(species)
        except KeyError as error:
            message = error.args[0] if error.args else str(error)
            raise ValueError(message) from error

    # ------------------------------------------------------------------
    def _build_species_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(1, weight=1)
        notebook.add(frame, text="Species")

        self.species_var = tk.StringVar()
        self.natdex_var = tk.StringVar()
        self.family_macro_var = tk.StringVar()
        self.display_name_var = tk.StringVar()
        self.category_var = tk.StringVar()
        self.cry_var = tk.StringVar()

        ttk.Label(frame, text="Species constant").grid(row=0, column=0, sticky="w")
        self.species_combo = ttk.Combobox(frame, textvariable=self.species_var, values=sorted(self.species_constants.keys()))
        self.species_combo.grid(row=0, column=1, sticky="ew")
        self.species_combo.bind("<<ComboboxSelected>>", self._on_species_selected)

        ttk.Label(frame, text="National Dex constant").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.natdex_combo = ttk.Combobox(frame, textvariable=self.natdex_var, values=sorted(self.natdex_constants.keys()))
        self.natdex_combo.grid(row=1, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(frame, text="Family macro").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.family_combo = ttk.Combobox(frame, textvariable=self.family_macro_var, values=self.family_macros)
        self.family_combo.grid(row=2, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(frame, text="Display name").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.display_name_var).grid(row=3, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(frame, text="Category name").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.category_var).grid(row=4, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(frame, text="Cry").grid(row=5, column=0, sticky="w", pady=(8, 0))
        self.cry_combo = ttk.Combobox(frame, textvariable=self.cry_var, values=self.cries)
        self.cry_combo.grid(row=5, column=1, sticky="ew", pady=(8, 0))

    # ------------------------------------------------------------------
    def _build_stats_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(2, weight=1)
        notebook.add(frame, text="Stats")

        stat_names = ["HP", "Attack", "Defense", "SpAttack", "SpDefense", "Speed"]
        self.base_stat_vars: Dict[str, tk.StringVar] = {}
        self.ev_vars: Dict[str, tk.StringVar] = {}

        ttk.Label(frame, text="Base Stats").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text="EV Yield").grid(row=0, column=1, sticky="w")

        for idx, stat in enumerate(stat_names, start=1):
            ttk.Label(frame, text=stat).grid(row=idx, column=0, sticky="w")
            base_var = tk.StringVar(value="0")
            ev_var = tk.StringVar(value="0")
            self.base_stat_vars[stat] = base_var
            self.ev_vars[stat] = ev_var
            ttk.Entry(frame, width=8, textvariable=base_var).grid(row=idx, column=0, sticky="e", padx=(80, 0))
            ttk.Entry(frame, width=5, textvariable=ev_var).grid(row=idx, column=1, sticky="w")

        ttk.Label(frame, text="Type 1").grid(row=1, column=2, sticky="w")
        ttk.Label(frame, text="Type 2").grid(row=2, column=2, sticky="w")
        self.type1_var = tk.StringVar(value="TYPE_NORMAL")
        self.type2_var = tk.StringVar(value="TYPE_NONE")
        type_values = sorted(self.type_constants)
        if "TYPE_NONE" not in type_values:
            type_values.append("TYPE_NONE")
        self.type1_combo = ttk.Combobox(frame, textvariable=self.type1_var, values=type_values)
        self.type2_combo = ttk.Combobox(frame, textvariable=self.type2_var, values=type_values)
        self.type1_combo.grid(row=1, column=3, sticky="ew")
        self.type2_combo.grid(row=2, column=3, sticky="ew")

        ttk.Label(frame, text="Ability 1").grid(row=3, column=2, sticky="w")
        ttk.Label(frame, text="Ability 2").grid(row=4, column=2, sticky="w")
        ttk.Label(frame, text="Hidden Ability").grid(row=5, column=2, sticky="w")
        ability_values = sorted(self.ability_constants)
        if "ABILITY_NONE" not in ability_values:
            ability_values.insert(0, "ABILITY_NONE")
        self.ability1_var = tk.StringVar(value="ABILITY_NONE")
        self.ability2_var = tk.StringVar(value="ABILITY_NONE")
        self.ability3_var = tk.StringVar(value="ABILITY_NONE")
        ttk.Combobox(frame, textvariable=self.ability1_var, values=ability_values).grid(row=3, column=3, sticky="ew")
        ttk.Combobox(frame, textvariable=self.ability2_var, values=ability_values).grid(row=4, column=3, sticky="ew")
        ttk.Combobox(frame, textvariable=self.ability3_var, values=ability_values).grid(row=5, column=3, sticky="ew")

        ttk.Label(frame, text="Catch Rate").grid(row=6, column=0, sticky="w", pady=(12, 0))
        self.catch_rate_var = tk.StringVar(value="45")
        ttk.Entry(frame, textvariable=self.catch_rate_var).grid(row=6, column=1, sticky="w", pady=(12, 0))

        ttk.Label(frame, text="Exp Yield").grid(row=7, column=0, sticky="w")
        self.exp_yield_var = tk.StringVar(value="64")
        ttk.Entry(frame, textvariable=self.exp_yield_var).grid(row=7, column=1, sticky="w")

        ttk.Label(frame, text="Growth Rate").grid(row=6, column=2, sticky="w", pady=(12, 0))
        self.growth_var = tk.StringVar(value=self.growth_rates[0] if self.growth_rates else "GROWTH_MEDIUM_FAST")
        ttk.Combobox(frame, textvariable=self.growth_var, values=self.growth_rates).grid(row=6, column=3, sticky="ew", pady=(12, 0))

        ttk.Label(frame, text="Egg Group 1").grid(row=7, column=2, sticky="w")
        ttk.Label(frame, text="Egg Group 2").grid(row=8, column=2, sticky="w")
        self.egg_group1_var = tk.StringVar(value=self.egg_groups[0] if self.egg_groups else "EGG_GROUP_NONE")
        self.egg_group2_var = tk.StringVar(value="EGG_GROUP_NONE")
        egg_values = self.egg_groups + (["EGG_GROUP_NONE"] if "EGG_GROUP_NONE" not in self.egg_groups else [])
        ttk.Combobox(frame, textvariable=self.egg_group1_var, values=egg_values).grid(row=7, column=3, sticky="ew")
        ttk.Combobox(frame, textvariable=self.egg_group2_var, values=egg_values).grid(row=8, column=3, sticky="ew")

        ttk.Label(frame, text="Gender Ratio").grid(row=8, column=0, sticky="w", pady=(12, 0))
        self.gender_ratio_var = tk.StringVar(value="PERCENT_FEMALE(50)")
        ttk.Entry(frame, textvariable=self.gender_ratio_var).grid(row=8, column=1, sticky="w", pady=(12, 0))

        ttk.Label(frame, text="Egg Cycles").grid(row=9, column=0, sticky="w")
        self.egg_cycles_var = tk.StringVar(value="20")
        ttk.Entry(frame, textvariable=self.egg_cycles_var).grid(row=9, column=1, sticky="w")

        ttk.Label(frame, text="Friendship").grid(row=9, column=2, sticky="w")
        self.friendship_var = tk.StringVar(value="STANDARD_FRIENDSHIP")
        ttk.Entry(frame, textvariable=self.friendship_var).grid(row=9, column=3, sticky="ew")

        ttk.Label(frame, text="Icon Palette Index").grid(row=10, column=2, sticky="w", pady=(12, 0))
        self.icon_palette_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.icon_palette_var).grid(row=10, column=3, sticky="ew", pady=(12, 0))

    # ------------------------------------------------------------------
    def _build_learnsets_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        notebook.add(frame, text="Learnsets")

        # Level-up
        level_frame = ttk.LabelFrame(frame, text="Level-up Moves", padding=8)
        level_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        level_frame.columnconfigure(0, weight=1)
        self.level_moves_state = LearnsetState(entries=[])
        self.level_listbox = tk.Listbox(level_frame, height=12)
        self.level_listbox.grid(row=0, column=0, columnspan=3, sticky="nsew")
        level_frame.rowconfigure(0, weight=1)
        level_scroll = ttk.Scrollbar(level_frame, orient="vertical", command=self.level_listbox.yview)
        level_scroll.grid(row=0, column=3, sticky="ns")
        self.level_listbox.configure(yscrollcommand=level_scroll.set)

        self.level_move_var = tk.StringVar()
        self.level_level_var = tk.StringVar(value="1")
        ttk.Label(level_frame, text="Move").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(level_frame, textvariable=self.level_move_var, values=self.move_constants).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(level_frame, text="Level").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(level_frame, textvariable=self.level_level_var, width=5).grid(row=1, column=2, sticky="e", pady=(8, 0))
        ttk.Button(level_frame, text="Add", command=self._add_level_move).grid(row=2, column=1, sticky="e", pady=(8, 0))
        ttk.Button(level_frame, text="Remove", command=self._remove_level_move).grid(row=2, column=2, sticky="e", pady=(8, 0))

        # Egg moves
        egg_frame = ttk.LabelFrame(frame, text="Egg Moves", padding=8)
        egg_frame.grid(row=0, column=1, sticky="nsew")
        egg_frame.columnconfigure(0, weight=1)
        self.egg_moves: List[str] = []
        self.egg_listbox = tk.Listbox(egg_frame, height=12)
        self.egg_listbox.grid(row=0, column=0, columnspan=2, sticky="nsew")
        egg_frame.rowconfigure(0, weight=1)
        egg_scroll = ttk.Scrollbar(egg_frame, orient="vertical", command=self.egg_listbox.yview)
        egg_scroll.grid(row=0, column=2, sticky="ns")
        self.egg_listbox.configure(yscrollcommand=egg_scroll.set)
        self.egg_move_var = tk.StringVar()
        ttk.Combobox(egg_frame, textvariable=self.egg_move_var, values=self.move_constants).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(egg_frame, text="Add", command=self._add_egg_move).grid(row=1, column=1, sticky="e", pady=(8, 0))
        ttk.Button(egg_frame, text="Remove", command=self._remove_egg_move).grid(row=2, column=1, sticky="e")

        # TM moves
        tm_frame = ttk.LabelFrame(frame, text="TM Moves", padding=8)
        tm_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        tm_frame.columnconfigure(0, weight=1)
        self.tm_moves: List[str] = []
        self.tm_listbox = tk.Listbox(tm_frame, height=10)
        self.tm_listbox.grid(row=0, column=0, columnspan=2, sticky="nsew")
        tm_scroll = ttk.Scrollbar(tm_frame, orient="vertical", command=self.tm_listbox.yview)
        tm_scroll.grid(row=0, column=2, sticky="ns")
        self.tm_listbox.configure(yscrollcommand=tm_scroll.set)
        self.tm_move_var = tk.StringVar()
        ttk.Combobox(tm_frame, textvariable=self.tm_move_var, values=self.move_constants).grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(tm_frame, text="Add", command=self._add_tm_move).grid(row=1, column=1, sticky="e", pady=(8, 0))
        ttk.Button(tm_frame, text="Remove", command=self._remove_tm_move).grid(row=2, column=1, sticky="e")

    # ------------------------------------------------------------------
    def _build_evolutions_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(0, weight=1)
        notebook.add(frame, text="Evolutions")

        self.evolutions: List[EvolutionEntry] = []
        self.evo_listbox = tk.Listbox(frame, height=15)
        self.evo_listbox.grid(row=0, column=0, columnspan=4, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        evo_scroll = ttk.Scrollbar(frame, orient="vertical", command=self.evo_listbox.yview)
        evo_scroll.grid(row=0, column=4, sticky="ns")
        self.evo_listbox.configure(yscrollcommand=evo_scroll.set)

        species_values = sorted(self.species_constants.keys())
        self.evo_from_var = tk.StringVar()
        self.evo_method_var = tk.StringVar(value=self.evolution_methods[0] if self.evolution_methods else "EVO_LEVEL")
        self.evo_param_var = tk.StringVar(value="0")
        self.evo_target_var = tk.StringVar()
        self.evo_conditions_var = tk.StringVar()

        ttk.Label(frame, text="From Species").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Combobox(frame, textvariable=self.evo_from_var, values=species_values).grid(row=1, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(frame, text="Method").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Combobox(frame, textvariable=self.evo_method_var, values=self.evolution_methods).grid(row=1, column=3, sticky="ew", pady=(8, 0))

        ttk.Label(frame, text="Parameter").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.evo_param_var).grid(row=2, column=1, sticky="ew")
        ttk.Label(frame, text="Target Species").grid(row=2, column=2, sticky="w")
        ttk.Combobox(frame, textvariable=self.evo_target_var, values=species_values).grid(row=2, column=3, sticky="ew")

        ttk.Label(frame, text="Conditions (comma-separated)").grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.evo_conditions_var).grid(row=3, column=2, columnspan=2, sticky="ew", pady=(8, 0))

        ttk.Button(frame, text="Add Evolution", command=self._add_evolution).grid(row=4, column=2, sticky="e", pady=(8, 0))
        ttk.Button(frame, text="Remove Selected", command=self._remove_evolution).grid(row=4, column=3, sticky="e", pady=(8, 0))

    # ------------------------------------------------------------------
    def _build_assets_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(1, weight=1)
        notebook.add(frame, text="Dex & Assets")

        self.height_var = tk.StringVar(value="10")
        self.weight_var = tk.StringVar(value="100")
        self.graphics_folder_var = tk.StringVar()

        ttk.Label(frame, text="Height (decimetres)").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.height_var).grid(row=0, column=1, sticky="ew")
        ttk.Label(frame, text="Weight (hectograms)").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.weight_var).grid(row=1, column=1, sticky="ew")

        ttk.Label(frame, text="Graphics folder").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.graphics_folder_var).grid(row=2, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(frame, text="Pokédex description").grid(row=3, column=0, sticky="nw", pady=(8, 0))
        self.description_text = tk.Text(frame, height=8, wrap="word")
        self.description_text.grid(row=3, column=1, sticky="nsew", pady=(8, 0))
        frame.rowconfigure(3, weight=1)

        self.asset_vars: Dict[str, tk.StringVar] = {}
        row = 4
        ttk.Label(frame, text="Assets").grid(row=row, column=0, sticky="w", pady=(12, 0))
        row += 1
        for label, (key, filetypes) in REQUIRED_ASSETS.items():
            self._add_asset_selector(frame, row, label, key, filetypes)
            row += 1
        for label, (key, filetypes) in OPTIONAL_ASSETS.items():
            self._add_asset_selector(frame, row, label, key, filetypes, optional=True)
            row += 1

    def _add_asset_selector(self, frame: ttk.Frame, row: int, label: str, key: str, filetypes, optional: bool = False) -> None:
        ttk.Label(frame, text=label + (" (optional)" if optional else "")).grid(row=row, column=0, sticky="w")
        var = tk.StringVar()
        self.asset_vars[key] = var
        entry = ttk.Entry(frame, textvariable=var)
        entry.grid(row=row, column=1, sticky="ew")
        ttk.Button(frame, text="Browse", command=lambda v=var, ft=filetypes: self._browse_for_file(v, ft)).grid(row=row, column=2, padx=(8, 0))

    # ------------------------------------------------------------------
    def _build_summary_tab(self, notebook: ttk.Notebook) -> None:
        frame = ttk.Frame(notebook, padding=12)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        notebook.add(frame, text="Summary")

        self.log_text = tk.Text(frame, state="disabled", wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

    # ------------------------------------------------------------------
    def _browse_for_file(self, var: tk.StringVar, filetypes) -> None:
        path = filedialog.askopenfilename(filetypes=[filetypes, ("All files", "*.*")])
        if path:
            var.set(path)

    # ------------------------------------------------------------------
    def _on_species_selected(self, _event=None) -> None:
        species = normalize_species_constant(self.species_var.get())
        self.species_var.set(species)
        default_folder = showdown_folder_from_species(species)
        if not self.graphics_folder_var.get():
            self.graphics_folder_var.set(default_folder)
        natdex = f"NATIONAL_DEX_{species[len('SPECIES_') :]}"
        if natdex in self.natdex_constants:
            self.natdex_var.set(natdex)
        meta = self.species_metadata.get(species)
        if meta and not self.display_name_var.get():
            self.display_name_var.set(meta.display_name)
        if meta and meta.height and not self.height_var.get():
            self.height_var.set(str(meta.height))
        if meta and meta.weight and not self.weight_var.get():
            self.weight_var.set(str(meta.weight))

    # ------------------------------------------------------------------
    def _add_level_move(self) -> None:
        move = self.level_move_var.get().strip()
        level_text = self.level_level_var.get().strip()
        if not move or not level_text:
            messagebox.showerror("Level-up Move", "Both move and level are required.")
            return
        move = move if move.startswith("MOVE_") else f"MOVE_{move.upper()}"
        try:
            level = int(level_text)
        except ValueError:
            messagebox.showerror("Level-up Move", "Level must be an integer.")
            return
        entry = LearnsetEntry(level=level, move=move)
        self.level_moves_state.add(entry)
        self._refresh_level_moves()

    def _remove_level_move(self) -> None:
        selection = self.level_listbox.curselection()
        if not selection:
            return
        self.level_moves_state.remove(selection[0])
        self._refresh_level_moves()

    def _refresh_level_moves(self) -> None:
        self.level_listbox.delete(0, tk.END)
        for display in self.level_moves_state.as_display():
            self.level_listbox.insert(tk.END, display)

    # ------------------------------------------------------------------
    def _add_egg_move(self) -> None:
        move = self.egg_move_var.get().strip()
        if not move:
            messagebox.showerror("Egg Move", "Select a move first.")
            return
        move = move if move.startswith("MOVE_") else f"MOVE_{move.upper()}"
        if move not in self.egg_moves:
            self.egg_moves.append(move)
            self.egg_moves.sort()
            self._refresh_egg_moves()

    def _remove_egg_move(self) -> None:
        selection = self.egg_listbox.curselection()
        if not selection:
            return
        self.egg_moves.pop(selection[0])
        self._refresh_egg_moves()

    def _refresh_egg_moves(self) -> None:
        self.egg_listbox.delete(0, tk.END)
        for move in self.egg_moves:
            self.egg_listbox.insert(tk.END, move)

    # ------------------------------------------------------------------
    def _add_tm_move(self) -> None:
        move = self.tm_move_var.get().strip()
        if not move:
            messagebox.showerror("TM Move", "Select a move first.")
            return
        move = move if move.startswith("MOVE_") else f"MOVE_{move.upper()}"
        if move not in self.tm_moves:
            self.tm_moves.append(move)
            self.tm_moves.sort()
            self._refresh_tm_moves()

    def _remove_tm_move(self) -> None:
        selection = self.tm_listbox.curselection()
        if not selection:
            return
        self.tm_moves.pop(selection[0])
        self._refresh_tm_moves()

    def _refresh_tm_moves(self) -> None:
        self.tm_listbox.delete(0, tk.END)
        for move in self.tm_moves:
            self.tm_listbox.insert(tk.END, move)

    # ------------------------------------------------------------------
    def _add_evolution(self) -> None:
        from_species = self.evo_from_var.get().strip()
        method = self.evo_method_var.get().strip()
        parameter = self.evo_param_var.get().strip()
        target = self.evo_target_var.get().strip()
        if not (from_species and method and target):
            messagebox.showerror("Evolutions", "From species, method, and target species are required.")
            return
        conditions_text = self.evo_conditions_var.get().strip()
        conditions = [cond.strip() for cond in conditions_text.split(",") if cond.strip()]
        entry = EvolutionEntry(
            from_species=normalize_species_constant(from_species),
            method=method,
            parameter=parameter or "0",
            target_species=normalize_species_constant(target),
            conditions=conditions,
        )
        self.evolutions.append(entry)
        self._refresh_evolutions()

    def _remove_evolution(self) -> None:
        selection = self.evo_listbox.curselection()
        if not selection:
            return
        self.evolutions.pop(selection[0])
        self._refresh_evolutions()

    def _refresh_evolutions(self) -> None:
        self.evo_listbox.delete(0, tk.END)
        for evo in self.evolutions:
            conds = ", ".join(evo.conditions) if evo.conditions else ""
            display = f"{evo.from_species} -> {evo.target_species} ({evo.method} {evo.parameter})"
            if conds:
                display += f" [{conds}]"
            self.evo_listbox.insert(tk.END, display)

    # ------------------------------------------------------------------
    def log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.configure(state="disabled")
        self.log_text.see(tk.END)

    # ------------------------------------------------------------------
    def generate(self) -> None:
        try:
            data = self._collect_data()
            assets = self._build_asset_bundle()
            self.log("Validating configuration…")
            self._apply_changes(data, assets)
            messagebox.showinfo("Success", "Pokémon data generated successfully.")
        except PillowUnavailableError as error:
            messagebox.showerror("Pillow missing", str(error))
        except Exception as error:  # pragma: no cover - defensive UI handling
            traceback.print_exc()
            messagebox.showerror("Error", str(error))
            self.log(f"Error: {error}")

    # ------------------------------------------------------------------
    def _collect_data(self) -> PokemonData:
        species = normalize_species_constant(self.species_var.get())
        if not species:
            raise ValueError("Species constant is required.")
        ensure_constant_exists(self.species_constants, species)

        natdex = normalize_natdex_constant(self.natdex_var.get())
        ensure_constant_exists(self.natdex_constants, natdex)

        family_macro = self.family_macro_var.get().strip()
        if not family_macro:
            raise ValueError("Family macro is required.")

        display_name = self.display_name_var.get().strip()
        category = self.category_var.get().strip()
        if not display_name or not category:
            raise ValueError("Display name and category are required.")

        cry = self.cry_var.get().strip()
        if not cry:
            raise ValueError("Please select a cry.")

        base_stats = {stat: int(self.base_stat_vars[stat].get()) for stat in self.base_stat_vars}
        ev_yield = {stat: int(self.ev_vars[stat].get()) for stat in self.ev_vars}

        types = [self.type1_var.get().strip(), self.type2_var.get().strip()]
        types = [typ for typ in types if typ]
        if not types:
            raise ValueError("At least one type must be selected.")

        abilities = [self.ability1_var.get().strip(), self.ability2_var.get().strip(), self.ability3_var.get().strip()]
        abilities = [ability for ability in abilities if ability]
        if not abilities:
            abilities = ["ABILITY_NONE"]

        catch_rate = int(self.catch_rate_var.get())
        exp_yield = int(self.exp_yield_var.get())
        growth_rate = self.growth_var.get().strip()
        egg_groups = [self.egg_group1_var.get().strip(), self.egg_group2_var.get().strip()]
        egg_groups = [group for group in egg_groups if group]
        if not egg_groups:
            egg_groups = ["EGG_GROUP_NONE"]
        gender_ratio = self.gender_ratio_var.get().strip()
        egg_cycles = int(self.egg_cycles_var.get())
        friendship = self.friendship_var.get().strip()

        icon_pal_index = self.icon_palette_var.get().strip()
        icon_pal = int(icon_pal_index) if icon_pal_index else None

        learnset_level = [LearnsetEntry(entry.level, entry.move) for entry in self.level_moves_state.entries]
        learnset_egg = list(self.egg_moves)
        learnset_tm = list(self.tm_moves)

        height = int(self.height_var.get())
        weight = int(self.weight_var.get())
        description = self.description_text.get("1.0", tk.END).strip()
        if not description:
            raise ValueError("Pokédex description is required.")

        evolutions = [
            EvolutionEntry(
                from_species=entry.from_species,
                method=entry.method,
                parameter=entry.parameter,
                target_species=entry.target_species,
                conditions=list(entry.conditions),
            )
            for entry in self.evolutions
        ]

        graphics_folder = self.graphics_folder_var.get().strip() or showdown_folder_from_species(species)

        dex_hint = {"height": height, "weight": weight}

        pokemon = PokemonData(
            species_constant=species,
            family_macro=family_macro,
            national_dex_constant=natdex,
            display_name=display_name,
            category_name=category,
            description=description,
            height=height,
            weight=weight,
            types=types,
            abilities=abilities,
            catch_rate=catch_rate,
            exp_yield=exp_yield,
            growth_rate=growth_rate,
            egg_groups=egg_groups,
            gender_ratio=gender_ratio,
            egg_cycles=egg_cycles,
            friendship=friendship,
            base_stats=base_stats,
            ev_yield=ev_yield,
            learnset_level_up=learnset_level,
            learnset_egg=learnset_egg,
            learnset_tm=learnset_tm,
            evolutions=evolutions,
            dex_order_hint=dex_hint,
            cry=cry,
            graphics_folder=graphics_folder,
            icon_pal_index=icon_pal,
        )
        return pokemon

    # ------------------------------------------------------------------
    def _build_asset_bundle(self) -> AssetBundle:
        missing = [label for label, (key, _) in REQUIRED_ASSETS.items() if not self.asset_vars.get(key, tk.StringVar()).get()]
        if missing:
            raise ValueError(f"Missing required asset(s): {', '.join(missing)}")

        optional_assets: Dict[str, Path] = {}
        for label, (key, _) in OPTIONAL_ASSETS.items():
            value = self.asset_vars.get(key)
            if not value:
                continue
            path = value.get().strip()
            if not path:
                continue
            if key.endswith(".png"):
                optional_assets[key] = Path(path)

        shiny_var = self.asset_vars.get("shiny_palette")
        shiny_path = Path(shiny_var.get()) if shiny_var and shiny_var.get().strip() else None

        cry_var = self.asset_vars.get("cry_sample")
        cry_path = Path(cry_var.get()) if cry_var and cry_var.get().strip() else None

        bundle = AssetBundle(
            front=Path(self.asset_vars["front"].get()),
            back=Path(self.asset_vars["back"].get()),
            icon=Path(self.asset_vars["icon"].get()),
            normal_palette=Path(self.asset_vars["normal_palette"].get()),
            shiny_palette=shiny_path,
            optional_assets=optional_assets,
            cry_sample=cry_path,
        )
        return bundle

    # ------------------------------------------------------------------
    def _apply_changes(self, data: PokemonData, assets: AssetBundle) -> None:
        generate_pokemon_assets(data, assets, logger=self.log)


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Pokémon JSON Generator")
    parser.add_argument(
        "--config",
        type=Path,
        help="Run in headless mode using the provided JSON configuration file.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        help="Optional path to write a JSON summary when using --config.",
    )
    parser.add_argument(
        "--database-path",
        type=Path,
        help="Optional path to the SQLite database used for stored Pokémon entries.",
    )
    parser.add_argument(
        "--store-database",
        action="store_true",
        help="When used with --config, store the generated Pokémon in the database.",
    )
    args = parser.parse_args(argv)

    if args.summary_output and not args.config:
        parser.error("--summary-output requires --config")
    if args.store_database and not args.config:
        parser.error("--store-database requires --config")

    if args.config:
        try:
            run_headless(args.config, args.summary_output, args.database_path, args.store_database)
        except PillowUnavailableError as error:
            print(f"Pillow missing: {error}", file=sys.stderr)
            raise SystemExit(1)
        except Exception as error:  # pragma: no cover - defensive CLI handling
            traceback.print_exc()
            raise SystemExit(1)
        return

    app = PokemonApp(database_path=args.database_path)
    app.mainloop()


if __name__ == "__main__":
    main()
