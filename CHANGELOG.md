# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] — Unreleased

First public release.

### Features
- **Hierarchical BFS feature augmentation** based on Hacar, Altafini & Cutini (2024).
  For each road segment, attribute values from L1, L2, …, LN BFS neighbours are aggregated
  and appended as new columns.
- **Multi-field selection** — augment any number of numeric fields in a single run.
- **Per-field neighbourhood depth (N)** — each field can specify its own BFS depth (1–100).
- **Per-field aggregation method** — independent choice per field from
  `mean · sum · min · max · median · std`.
- **Automatic neighbour-count columns** — `L1_Count … LN_Count` are always appended
  (N = max depth across all selected fields).
- **Two interfaces**:
  - **Processing Toolbox** algorithm under *Network Analysis* (automatable, scriptable).
  - **Dock panel** with interactive per-field configuration, output naming,
    progress bar, and live log.
- **`PER_FIELD_CONFIG` advanced string parameter** for programmatic use:
  `fieldname:N:method, …`
- **Field-major output schema**: each field gets its own consecutive
  `L1_field … LN_field` block, followed by the count columns.
- **BFS exhaustion handling**: when a BFS branch becomes empty before reaching the
  requested depth, remaining levels are left `NULL` (no spurious repeated values).
