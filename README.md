# grammar-accuracy

![License: MIT](https://img.shields.io/badge/license-MIT-blue) ![Python 3.14+](https://img.shields.io/badge/python-3.14%2B-blue)

How often a tree-sitter grammar builds the same tree as the language's own parser, node by node.

An error check ("does the file parse?") cannot see a wrong tree that has no ERROR in it, such as
`[*a.b()]` read as `(*a).b()`. This harness counts those. It started as
`scripts/tree-accuracy.mjs` in [inth3shadows/tree-sitter-typescript](https://github.com/inth3shadows/tree-sitter-typescript)
(against tsc). This repo applies the same method to other grammars, one language at a time.

| Language | Grammar | Oracle |
|---|---|---|
| Python | tree-sitter-python | CPython `ast.parse` |

## Method (Python)

- **Oracle**: `ast.parse` of the CPython that runs the harness (3.14; `requires-python >= 3.14`).
  Parse only, nothing is compiled or run.
- **Files**: every `.py` file in the pinned corpora (`pins.json`) that `ast.parse` accepts and that is
  UTF-8: CPython `Lib/` at v3.14.0, Django 5.2.8, pydantic v2.12.4. That is 4,911 files.
- **Unit**: a node as `(category, start byte, end byte)`. Each side's node kinds map to shared
  categories: binary, boolean, compare, unary, await, call, member, subscript, ternary, lambda,
  walrus, yield, spread, comprehension, slice. Annotation nodes (`generic_type`, `union_type`,
  `splat_type`, `member_type`) map to the expression categories, since ast has no type nodes.
- **Precision** = matched / nodes the grammar emits. **Recall** = matched / nodes the oracle emits.
  A wrong nesting costs both: the wrong node is unmatched and the oracle's node is missing.
- **Builds**: a grammar's committed `src/parser.c` (+ `scanner.c`), compiled with `cc` and cached
  by content hash. No tree-sitter CLI needed.

Differences the grammar cannot change are left out on both sides (details in
`src/grammar_accuracy/python.py`): parentheses, the inner links of `a and b and c`, `**d` in dict
literals, `*args` in parameter lists, match-statement patterns, string nodes (their inner
expressions still count), tuples, and PEP 695 type-parameter declarations.

## Results

Measured 2026-11-17 with CPython 3.14.5. Full numbers per category: `results/`.

| Build | Commit | Precision % | Recall % | Wrong | Missed | Error files |
|---|---|---|---|---|---|---|
| tree-sitter-python v0.25.0 | 293fdc0 | 99.992 | 99.989 | 111 | 154 | 4 |

Wrong trees in v0.25.0 that the run surfaced. Each was confirmed by parsing a minimal snippet:

| Input | tree-sitter-python reads it as | Category |
|---|---|---|
| `[*a.b()]`, `{*range(4)}`, `x[*a[b]]` | `(*a).b()`: splat binds tighter than call, attribute, subscript | spread, call, member, subscript |
| `type(s).p = 1` | a `type_alias_statement` with left side `(s).p` | call, member |
| `a ^ b & c` | `(a ^ b) & c`; `&` should bind tighter | binary |
| `x: list[int] \| str \| None` | `list[int] \| (str \| None)` | binary |
| `f'{x:=10}'` | walrus `x := 10`; it is `x` with format spec `=10` | walrus |
| `def f(x: a[b:c])` | ERROR: no slices in annotations | slice |
| `(bar.\n    baz)` | ERROR: attribute access split over a line inside parentheses | member |

Not yet examined: the rest of the call and subscript misses, and the 4 error files
(`results/*.json` lists them).

## Prerequisites

- Python 3.14+ and [uv](https://docs.astral.sh/uv/)
- A C compiler (`cc`) and `git`
- Network access for the first `fetch` (GitHub)

## Reproduce

```sh
uv sync
uv run grammar-accuracy fetch                 # pinned grammar + corpora into ~/.cache/grammar-accuracy
uv run grammar-accuracy run --categories      # about a minute
uv run grammar-accuracy run \
  --build upstream=~/.cache/grammar-accuracy/grammars/upstream-293fdc02038e \
  --build fork=/path/to/tree-sitter-python    # several builds in one pass; ast parses each file once
uv run grammar-accuracy run --show 20 --show-category spread   # print mismatched nodes with source
uv run pytest
```

`--build` takes a grammar checkout, its `src/`, or a compiled `.so`. `GRAMMAR_ACCURACY_CACHE`
moves the cache.

## Project Structure

- `src/grammar_accuracy/harness.py`: fetching, compiling grammar builds, scoring, CLI
- `src/grammar_accuracy/python.py`: the Python oracle and category mapping
- `pins.json`: pinned grammar and corpus commits
- `results/`: recorded runs
- `tests/`: the harness's own tests

## Related Documentation

- [Technical Reference](TECHNICAL.md): architecture, design decisions, configuration, limitations
- [Usage Guide](USAGE.md): how to read the results

<!-- docvet:anchors
GRAMMAR_ACCURACY_CACHE -> src/grammar_accuracy/harness.py
-->
