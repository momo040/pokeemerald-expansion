# Pokémon JSON GUI Tool

This tool provides a Tkinter-based workflow for creating the JSON assets that
`json_data_rules.mk` expects when adding a brand-new Pokémon family.  It guides
you through the species metadata, learnsets, evolutions, Pokédex text, graphics
assets, cry selection, and dex ordering so that the generated files can be fed
into the build system for automatic C source generation.

The utility performs a large set of quality-of-life checks while you work:

* Species, move, ability, item, and method dropdowns are automatically populated
  from the existing project headers, guaranteeing valid symbols.
* The active configuration is inspected to make sure the chosen family macro is
  enabled in `include/config/species_enabled.h`.  If it is not, the tool will
  toggle it for you.
* Front, back, icon, and optional animation PNGs are validated so they always
  have the correct dimensions (64×64 for fronts/backs, 32×32 for icons, 64×64 for
  animation frames).
* Palettes are required to be JASC-PAL files with exactly sixteen entries.  When
  a shiny palette is not supplied the tool automatically derives one from the
  normal palette so that builds never fail due to missing data.
* Graphics are copied into `graphics/pokemon/<folder>/…` using the expected
  filenames.  Missing folders are created on demand.
* JSON files are emitted beneath `data/json/pokemon/<folder>/` using the layout
  expected by `json_data_rules.mk`.  These include base stats, learnsets,
  evolutions, Pokédex text, names, and dex ordering metadata.
* The National Dex ordering tables in
  `src/data/pokemon/pokedex_orders.h` are updated so alphabetical, height, and
  weight lists stay sorted.
* `sound/cry_tables.inc` is updated in both the forward and reverse cry tables,
  mapping the new species to either an existing cry or a newly supplied one.
* Sprite palettes, cry choices, and dex names are checked to ensure the species
  constant already exists in the tree.

## Running the tool

```bash
python3 tools/pokemon_json_gui/main.py
```

If Pillow is not installed you will be prompted to add it.  The package is
required for sprite dimension and palette validation.

### Headless / Docker usage

The generator can also run without a GUI, which is convenient when driving it
from Docker or CI environments. Provide a configuration file describing the
Pokémon data and asset locations:

```bash
python3 tools/pokemon_json_gui/main.py \
    --config docker_config.json \
    --summary-output build/pokemon_summary.json
```

The configuration file must define two objects:

```json
{
  "pokemon": {
    "species_constant": "SPECIES_EXAMPLEMON",
    "family_macro": "P_FAMILY_EXAMPLEMON",
    "national_dex_constant": "NATIONAL_DEX_EXAMPLEMON",
    "display_name": "Examplemon",
    "category_name": "Example",
    "description": "Examplemon loves dockerized workflows.",
    "height": 10,
    "weight": 200,
    "types": ["TYPE_NORMAL"],
    "abilities": ["ABILITY_RUN_AWAY"],
    "catch_rate": 45,
    "exp_yield": 64,
    "growth_rate": "GROWTH_FAST",
    "egg_groups": ["EGG_GROUP_FIELD"],
    "gender_ratio": "MON_GENDERLESS",
    "egg_cycles": 20,
    "friendship": "STANDARD_FRIENDSHIP",
    "base_stats": {"hp": 60, "attack": 60, "defense": 60, "speed": 60, "spAttack": 60, "spDefense": 60},
    "ev_yield": {"hp": 2},
    "learnset_level_up": [{"level": 1, "move": "MOVE_TACKLE"}],
    "learnset_egg": [],
    "learnset_tm": ["MOVE_PROTECT"],
    "evolutions": [],
    "cry": "Cry_Pidgey",
    "graphics_folder": "examplemon"
  },
  "assets": {
    "front": "assets/front.png",
    "back": "assets/back.png",
    "icon": "assets/icon.png",
    "normal_palette": "assets/normal.pal",
    "shiny_palette": "assets/shiny.pal",
    "optional_assets": {
      "anim_front.png": "assets/anim_front.png"
    },
    "cry_sample": "assets/examplemon.aif"
  }
}
```

`learnset_level_up` entries require objects containing a `level` and `move`,
while `evolutions` accept the same keys used by the GUI (`from`, `method`,
`parameter`, `to`, and optional `conditions`).

`--summary-output` writes a recap of the generated data to the specified path.
Alternatively, the JSON configuration can include a `"summary_output"` field.

### Database integration

The GUI now includes database-aware workflows so that created Pokémon can be
reused later or automatically applied to the repository:

* **Save to Database** stores the current configuration (including asset file
  paths) inside `build/pokemon_json_gui/pokemon.db` by default.
* **Open Database…** opens a browser listing the stored entries.  From there you
  can load a Pokémon back into the editor or apply it directly to the project,
  which runs the same generation pipeline used by the main "Generate" button.

Headless runs can participate in the same database by providing the
`--store-database` flag.  Both GUI and CLI modes accept `--database-path` when
you wish to override the default SQLite file location.

## Generated files

For a species folder named `examplemon` the tool generates the following
structure:

```
data/json/pokemon/examplemon/
├── base_stats.json
├── evolutions.json
├── learnsets/
│   ├── egg.json
│   ├── level_up.json
│   └── tm.json
├── names.json
└── pokedex.json
```

JSON files follow the data layout used by the templates in
`json_data_rules.mk`, allowing `make` to translate them into C sources.

The tool also copies graphical assets into
`graphics/pokemon/examplemon/` and, when requested, adds new cry data under
`sound/`.
