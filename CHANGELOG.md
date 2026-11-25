# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- `pins.json` is keyed by language.
- pytest 9.0.3 (Dependabot: vulnerable tmpdir handling, dev only).

### Added
- grammar-orchard builds: `tree_sitter_<lang>_orchard` symbols load; a checkout without generated files says so. Python and JavaScript orchard forks measured (`results/*-orchard-2026-11-24.json`).
- JavaScript: tree-sitter-javascript vs the TypeScript compiler's parser (Node helper `oracles/javascript/`), with node, webpack, three.js and test262 corpora; `--lang`.
- Corpus `skip_if` regex in `pins.json`.
- Fork sweep: 54 tree-sitter-python fork branches scored, `results/python-forks-2026-11-17.json`.
- Older grammars with a C++ `scanner.cc` compile (c++ driver).
- Python tree-accuracy harness: tree-sitter-python builds scored node by node against CPython `ast.parse`.
- `grammar-accuracy fetch` / `run` CLI with `--build`, `--corpus`, `--json`, `--categories`, `--show`.
- First measurement of tree-sitter-python v0.25.0 in `results/`.
