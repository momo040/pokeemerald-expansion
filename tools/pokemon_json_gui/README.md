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
