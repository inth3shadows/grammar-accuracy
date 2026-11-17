# Technical Reference: grammar-accuracy

## Architecture

```
pins.json ──fetch──> ~/.cache/grammar-accuracy/{grammars,corpora}/<name>-<sha12>/
                                   │
--build NAME=PATH ──cc -shared──> builds/<content-hash>.so ──ctypes + PyCapsule──> tree_sitter.Language
                                   │
for each corpus file:  oracle_nodes(bytes)  ─┐
                       grammar_nodes(tree)  ─┴─> Score: per-category grammar / oracle / matched
                                                  └─> table, --categories, --show, --json
```

- `harness.py` knows nothing about Python syntax: fetching, compiling, loading, scoring and the CLI.
- Each language is a module (`python.py`, `javascript.py`): file extensions, the C symbol, the
  category maps, the convention skips, and the two node extractors. `harness.py` uses five of its
  names (`EXTS`, `SYMBOL`, `oracle_name`, `oracle_nodes`, `grammar_nodes`) and picks the module
  with `--lang` from `LANGS`. A new language is a module with the same five, plus a `pins.json` entry.
- An oracle that does not run in Python runs as a long-lived helper process speaking one JSON
  object per line: `{"src": text}` in, `{"nodes": [[category, startByte, endByte], ...]}` or
  `{"rejected": reason}` out, offsets already converted to UTF-8 bytes. `oracles/javascript/oracle.mjs`
  is the first; one process serves a whole run.
- The oracle parses each file once per run, however many builds are passed.

Design decisions:
- **Compile committed `src/parser.c`, not `grammar.js`.** (`c++` when the scanner is an older `scanner.cc`.) It measures what a grammar actually ships
  and needs only `cc`, not the tree-sitter CLI or Node.
- **PyCapsule, not an int pointer.** py-tree-sitter 0.25 deprecates `Language(int)`.
- **Sets, not multisets.** Two nodes of one category with the same span are counted once on both
  sides, as in the TypeScript harness.
- **Byte offsets.** ast columns are UTF-8 byte offsets, so non-UTF-8 files are rejected rather than
  mis-measured. ast drops a BOM from line 1's columns; the harness adds it back.

## File Descriptions

| File | Purpose |
|---|---|
| `src/grammar_accuracy/harness.py` | Pins, fetch, compile/load builds, `Score`, CLI (`fetch`, `run`) |
| `src/grammar_accuracy/python.py` | Python category maps, convention skips, `oracle_nodes`, `grammar_nodes` |
| `src/grammar_accuracy/javascript.py` | JavaScript mapping; starts and talks to the Node oracle helper |
| `oracles/javascript/oracle.mjs` | tsc-based JavaScript oracle (typescript pinned in its `package-lock.json`) |
| `src/grammar_accuracy/__main__.py` | `python -m grammar_accuracy` |
| `pins.json` | Per language: pinned grammar commits (default builds) and corpus commits; a corpus's optional `skip_if` regex excludes files by content |
| `tests/test_python.py`, `tests/test_javascript.py` | Per-category agreement, convention skips, byte offsets, wrong-tree canary, score arithmetic |
| `results/` | `--json` output of recorded runs |

## Configuration

| Name | Default | Purpose |
|---|---|---|
| `GRAMMAR_ACCURACY_CACHE` | `~/.cache/grammar-accuracy` | Where grammars, corpora and compiled builds live |

Changing a pin: edit `pins.json` (`sha` is what is fetched and verified; `ref` is a label), then
`grammar-accuracy fetch`. A fetched commit that does not match its pin exits non-zero.

## Maintenance Commands

```sh
uv run pytest                                          # tests (fetch + compile the pinned grammar once)
uv run grammar-accuracy run --categories --json results/<name>.json
uv run grammar-accuracy run --show 20 --show-category member     # inspect mismatches
uv lock --upgrade-package tree-sitter                  # then re-run tests and a full run
```

## Known Limitations

- The oracle is whichever CPython runs the harness (`requires-python >= 3.14`). A newer CPython can
  accept syntax an older one rejects, so record the version with every result (the `--json` output does).
- Only expressions are measured. Statements, tuples, strings, patterns and PEP 695 declarations are
  left out, so a grammar can be wrong there without the score moving.
- `--show` prints mismatches for the first build only.
- Files are read and parsed one at a time in one process; a full run takes about a minute.
- tsc is lenient as a JavaScript oracle: it accepts a few early errors (`a ?? b || c`) that a spec
  parser rejects. test262's negative tests are skipped by their frontmatter for that reason.
- tsc decides module or script from the file's own imports and exports, so test262's module-only
  tests are skipped rather than mis-parsed as scripts.

<!-- docvet:anchors
GRAMMAR_ACCURACY_CACHE -> src/grammar_accuracy/harness.py
grammar_nodes -> src/grammar_accuracy/python.py
oracle_nodes -> src/grammar_accuracy/python.py
-->
