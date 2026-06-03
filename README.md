# Network Hierarchical Augmentation — QGIS Plugin

A QGIS plugin that augments road network features with aggregated attribute values from hierarchical BFS neighbourhoods (L1, L2, …, LN). Built on the method described in **Hacar, Altafini & Cutini (2024)**.

> Per-field neighbourhood depth · Per-field aggregation · Automatic neighbour counts · Available both in the Processing Toolbox and as a dock panel.

---

## What it does

For every road segment in the input network, the plugin walks the topology outward using **Breadth-First Search (BFS)** and aggregates the values of one or more numeric fields at each level:

```
For road  ★ :
  L1_field  =  AGG( field(c) : c ∈ direct neighbours of ★ )
  L2_field  =  AGG( field(c) : c ∈ neighbours of L1, excluding visited )
  …
  LN_field  =  AGG( field(c) : c ∈ neighbours of L(N-1), excluding visited )
```

The result is a new vector layer where each row carries its original attributes **plus** `Ln_<fieldname>` columns and automatic `Ln_Count` columns.

---

## Features

- **Multi-field selection** — augment any number of numeric fields in a single run
- **Per-field neighbourhood depth (N)** — each field can have its own depth (1–100)
- **Per-field aggregation method** — `mean · sum · min · max · median · std`
- **Automatic neighbour counts** — `L1_Count … LN_Count` columns are always generated
- **NULL on network boundary** — when a BFS branch is exhausted, remaining levels stay NULL (no spurious repeated values)
- **Two interfaces** — Processing Toolbox (automatable) and a dockable panel (interactive)
- **Reproducible** — same algorithm runs from both interfaces

---

## Installation

### From ZIP (recommended)

1. Download the latest release ZIP from the [Releases](../../releases) page.
2. In QGIS: **Plugins → Manage and Install Plugins… → Install from ZIP**
3. Select `NetworkHierarchicalAugmentation.zip`.

### From source

```bash
git clone https://github.com/hacarm/network-hierarchical-augmentation.git
cd network-hierarchical-augmentation
# Symlink (Linux/macOS) or copy the folder into your QGIS plugins directory:
#   Linux:   ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
#   macOS:   ~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/
#   Windows: %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\
ln -s "$(pwd)/NetworkHierarchicalAugmentation" \
      ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/NetworkHierarchicalAugmentation
```

Then in QGIS: **Plugins → Manage and Install Plugins… → Installed** and enable *Network-Based Hierarchical Feature Augmentation*.

---

## Usage

### Dock Panel (interactive)

1. Open the dock panel: **Plugins → Network Augmentation** (or the toolbar icon).
2. Pick a line layer as input.
3. Check the numeric fields you want to augment.
4. For each checked field, set its `Max N` and `Aggregation`.
5. Set the output layer name and click **Run Augmentation**.
6. The output layer is added to the project, with `Ln_<field>` and `Ln_Count` columns appended.

### Processing Toolbox (automatable)

Find it under **Network Analysis → Network-Based Hierarchical Feature Augmentation**.

Parameters:

| Parameter | Description |
|-----------|-------------|
| `INPUT` | Line vector layer |
| `FIELDS` | Numeric fields to augment (multi-select) |
| `MAX_N` | Default neighbourhood depth, used when no per-field override |
| `AGG_METHOD` | Default aggregation method |
| `PER_FIELD_CONFIG` | *(advanced)* `fieldname:N:method,…` overrides — e.g. `length:10:mean,population:5:sum` |
| `OUTPUT` | Output layer |

### From Python

```python
import processing

result = processing.run(
    'networkaugmentation:network_hierarchical_augmentation',
    {
        'INPUT':            'roads_layer',
        'FIELDS':           ['length', 'population', 'ped_count'],
        'MAX_N':            5,
        'AGG_METHOD':       0,                          # 0 = mean
        'PER_FIELD_CONFIG': 'length:10:mean,population:5:sum,ped_count:8:max',
        'OUTPUT':           'TEMPORARY_OUTPUT',
    },
)
augmented_layer = result['OUTPUT']
```

---

## Output schema

Output fields are appended after the original ones, in **field-major** order:

```
<original fields …>
L1_length, L2_length, …, L10_length,        # length block (N=10)
L1_population, L2_population, …, L5_population,   # population block (N=5)
L1_ped_count, L2_ped_count, …, L8_ped_count,      # ped_count block (N=8)
L1_Count, L2_Count, …, L10_Count             # auto-generated, N = max across fields
```

- Columns are typed as `Double` for aggregated values, `Int` for `Ln_Count`.
- If a BFS branch exhausts before reaching level *n*, the corresponding `Ln_*` cells stay `NULL`.

---

## Method reference

> **Hacar, M.; Altafini, D.; Cutini, V.** (2024). Network-Based Hierarchical Feature Augmentation for Predicting Road Classes in OpenStreetMap. *ISPRS International Journal of Geo-Information*, 13(12), 456. <https://doi.org/10.3390/ijgi13120456>

Please cite the paper if you use this plugin in academic work.

---

## Requirements

- QGIS **3.16** or later
- Python 3 (bundled with QGIS)
- No external Python dependencies

---

## Repository layout

```
NetworkHierarchicalAugmentation/
├── __init__.py        # classFactory entry point
├── metadata.txt       # QGIS plugin metadata
├── plugin.py          # registers provider + dock panel
├── provider.py        # QgsProcessingProvider
├── algorithm.py       # main BFS algorithm
├── panel.py           # QDockWidget UI
└── icon.svg           # plugin icon
```

---

## Contributing

Issues and pull requests are welcome. For larger changes please open an issue first to discuss.

---

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
