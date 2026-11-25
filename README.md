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
| JavaScript | tree-sitter-javascript | TypeScript compiler's parser (`ts.createSourceFile`, as .js) |

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
- **Builds**: a grammar's committed `src/parser.c` (+ `scanner.c`, or a C++ `scanner.cc`), compiled with `cc` (`c++` for a C++ scanner) and cached
  by content hash. No tree-sitter CLI needed.

Differences the grammar cannot change are left out on both sides (details in
`src/grammar_accuracy/python.py`): parentheses, the inner links of `a and b and c`, `**d` in dict
literals, `*args` in parameter lists, match-statement patterns, string nodes (their inner
expressions still count), tuples, and PEP 695 type-parameter declarations.

## Results (Python)

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

### grammar-orchard

[grammar-orchard](https://codeberg.org/grammar-orchard) maintains forks of unmaintained grammars.
Measured 2026-11-24, built from its GitHub mirror (the Codeberg repos don't track `parser.c`).
Full numbers: `results/python-orchard-2026-11-24.json`.

| Build | Commit | Precision % | Recall % | Wrong | Missed | Error files |
|---|---|---|---|---|---|---|
| tree-sitter-python v0.25.0 | 293fdc0 | 99.992 | 99.989 | 111 | 154 | 4 |
| tree-sitter-python-orchard 0.6.1 | f124a00 | 99.994 | 99.994 | 92 | 92 | 4 |

0.6.1 fixes `type(s).p = 1`, `a ^ b & c`, `f'{x:=10}'` and splats in list literals. Still wrong,
each confirmed with a minimal snippet: a splat in a set or subscript (`{*range(4)}` as
`(*range)(4)`, `x[*a[b]]` as `(*a)[b]`; spread 43 wrong / 41 missed), `list[int] | str | None`
nested to the right, and `def f(x: a[b:c])` read as a constrained type.

### Forks

Measured 2026-11-17 with the same files, oracle and rules. GitHub listed 238 direct forks of
tree-sitter/tree-sitter-python; 230 could be fetched (8 could not), with every branch.
A branch is included when its committed `src/parser.c` + `src/scanner.c` (or `scanner.cc`) match no
commit in upstream's history, it exports `tree_sitter_python`, and its ABI is 13 or newer (3 older
ones are left out). That leaves 54 forks' branches, plus upstream `master` and `v0.25.0`.
Rows are sorted by wrong + missed. Full numbers per category: `results/python-forks-2026-11-17.json`.

| Fork | Repo | Branch | Commit | Committed | Precision % | Recall % | Wrong | Missed | Error files |
|---|---|---|---|---|---|---|---|---|---|
| StudentWeis | tree-sitter-python | `fix/pep798-unpacking-comprehensions` | f9fbe8b | 2026-10-13 | 99.994 | 99.991 | 88 | 131 | 4 |
| dokimasia | tree-sitter-python | `master` | bab31bd | 2026-10-20 | 99.994 | 99.991 | 88 | 131 | 3 |
| zmaril | tree-sitter-python | `fix/dedent-inside-brackets-impl` | 9f8a317 | 2026-08-12 | 99.993 | 99.990 | 107 | 151 | 3 |
| etchpad | tree-sitter-python | `development` | 95eb676 | 2026-03-06 | 99.993 | 99.989 | 108 | 154 | 4 |
| JarvisDing-sdu | tree-sitter-python | `fix/return-tuple-splats` | c4050b0 | 2026-10-24 | 99.992 | 99.989 | 111 | 154 | 4 |
| QuiltLang | tree-sitter-python | `master` | a73c643 | 2026-09-07 | 99.992 | 99.989 | 111 | 154 | 4 |
| ZeroIntensity | tree-sitter-python | `lazy-import-syntax` | 6c03cce | 2026-05-19 | 99.992 | 99.989 | 111 | 154 | 4 |
| cperivol | tree-sitter-python | `master` | ca7c85a | 2025-09-12 | 99.992 | 99.989 | 111 | 154 | 4 |
| seanmozeik | tree-sitter-python | `codex-comment-indent` | da2cb9d | 2026-10-03 | 99.992 | 99.989 | 111 | 154 | 4 |
| sontek | tree-sitter-python | `fix/serialize-buffer-overrun` | a81938d | 2026-09-24 | 99.992 | 99.989 | 111 | 154 | 4 |
| **tree-sitter** | tree-sitter-python | `master` | 26855ea | 2025-09-15 | 99.992 | 99.989 | 111 | 154 | 4 |
| **tree-sitter** | tree-sitter-python | `v0.25.0` | 293fdc0 | 2025-09-11 | 99.992 | 99.989 | 111 | 154 | 4 |
| uncertaintea-io | tree-sitter-python | `master` | 24978ae | 2026-09-27 | 99.992 | 99.989 | 111 | 154 | 4 |
| wotjr1649 | tree-sitter-python | `fix/await-power-precedence` | 64c5dca | 2026-11-16 | 99.992 | 99.989 | 111 | 154 | 4 |
| zmaril | tree-sitter-python | `fix/dedent-inside-brackets` | 87d3c93 | 2026-08-11 | 99.992 | 99.989 | 111 | 154 | 4 |
| skakun-editor | tree-sitter-python | `master` | e6fb036 | 2025-08-02 | 99.992 | 99.989 | 115 | 159 | 9 |
| DennySun2020 | tree-sitter-python | `master` | a0b0da4 | 2023-12-27 | 99.992 | 99.989 | 115 | 166 | 15 |
| IsaacFedorov | tree-sitter-python | `simplify-try-statement` | 136dda3 | 2025-05-28 | 99.992 | 99.989 | 115 | 166 | 9 |
| joelvaneenwyk | tree-sitter-python | `master` | 8dd2d4a | 2025-02-12 | 99.992 | 99.989 | 115 | 166 | 9 |
| zed-industries | tree-sitter-python | `fix-try` | afab593 | 2025-06-26 | 99.992 | 99.989 | 115 | 166 | 9 |
| rilevera | tree-sitter-python | `hotfix/export-highlights` | 56861a4 | 2026-09-10 | 99.992 | 99.987 | 123 | 184 | 6 |
| rilevera | tree-sitter-python | `main` | 5c9f180 | 2026-09-25 | 99.992 | 99.987 | 123 | 184 | 6 |
| skakun-editor | tree-sitter-python | `upstream` | 5c0d12a | 2025-07-25 | 99.989 | 99.989 | 161 | 159 | 9 |
| 01000100GT | tree-sitter-python | `reserved` | 258dc6b | 2024-11-24 | 99.988 | 99.989 | 172 | 166 | 9 |
| chaneyzorn | tree-sitter-python | `master` | 16c3df3 | 2024-07-28 | 99.988 | 99.989 | 172 | 166 | 9 |
| elisiariocouto | tree-sitter-python | `feat/string-prefixes` | 2340376 | 2024-12-17 | 99.988 | 99.989 | 172 | 166 | 9 |
| jasontatton | tree-sitter-python | `master` | 45a4eb8 | 2023-08-16 | 99.988 | 99.989 | 172 | 166 | 14 |
| jqcorreia | tree-sitter-python | `master` | 3717e77 | 2024-12-16 | 99.988 | 99.989 | 172 | 166 | 9 |
| llllvvuu | tree-sitter-python | `wip/double_comment` | 7055356 | 2023-09-21 | 99.988 | 99.989 | 172 | 166 | 14 |
| llllvvuu | tree-sitter-python | `wip/double_comment_2` | 3511972 | 2023-09-22 | 99.988 | 99.989 | 172 | 166 | 14 |
| meirdev | tree-sitter-python-jsx | `fixes` | 9ce25f2 | 2024-06-08 | 99.988 | 99.989 | 172 | 166 | 9 |
| panekj | tree-sitter-python | `lapce/0.4.0` | 5330f4d | 2024-06-08 | 99.988 | 99.989 | 172 | 166 | 9 |
| sourcery-ai | tree-sitter-python | `ben/fix-update-tree-sitter` | a412859 | 2023-11-07 | 99.988 | 99.988 | 172 | 170 | 17 |
| vanessa-rodrigues | tree-sitter-python | `parsing_errors` | 6e03907 | 2025-12-09 | 99.985 | 99.985 | 211 | 213 | 3 |
| vanessa-rodrigues | tree-sitter-python | `type_alias` | b0bc61d | 2025-11-26 | 99.985 | 99.985 | 211 | 215 | 4 |
| guidocalvano | tree-sitter-python | `feature/context_aware` | 9e623d0 | 2022-11-03 | 99.985 | 99.982 | 223 | 264 | 45 |
| sourcery-ai | tree-sitter-python | `brendan/feat/captures` | 4f56cef | 2022-12-06 | 99.984 | 99.981 | 232 | 273 | 45 |
| sourcery-ai | tree-sitter-python | `master` | 187e8dc | 2023-01-19 | 99.984 | 99.981 | 232 | 273 | 45 |
| sourcery-ai | tree-sitter-python | `nick/fix/with-item-precedence` | d0eca66 | 2022-11-17 | 99.984 | 99.981 | 232 | 273 | 45 |
| Britefury | tree-sitter-python | `britefury/fields-complete-ast` | d42a61b | 2025-10-26 | 99.992 | 99.971 | 111 | 425 | 5 |
| Britefury | tree-sitter-python | `britefury/fields` | e9ffda1 | 2024-11-23 | 99.968 | 99.969 | 461 | 455 | 9 |
| sourcery-ai | tree-sitter-python | `nick/chore/jan-23-rebase` | e2c0060 | 2023-01-19 | 99.978 | 99.946 | 312 | 776 | 40 |
| resin-studio | tree-sitter-python | `master` | 0d1cdaf | 2022-07-26 | 99.977 | 99.947 | 328 | 773 | 40 |
| Desdaemon | tree-sitter-python | `master` | 1978b7c | 2024-03-14 | 99.985 | 99.902 | 220 | 1,419 | 128 |
| ahlinc | tree-sitter-python | `master` | 64cc814 | 2023-03-11 | 99.825 | 99.842 | 2,529 | 2,281 | 37 |
| theHamsta | tree-sitter-python | `match-block` | ac9605b | 2023-08-04 | 99.802 | 99.856 | 2,873 | 2,087 | 25 |
| venicteam | tree-sitter-python | `master` | 984165e | 2022-09-01 | 99.698 | 99.946 | 4,379 | 776 | 46 |
| lnay | tree-sitter-sage | `master` | 6c42966 | 2024-12-03 | 99.809 | 99.827 | 2,766 | 2,505 | 64 |
| m-novikov | tree-sitter-python | `debug-strings` | 154bf6b | 2021-06-05 | 99.753 | 99.824 | 3,576 | 2,551 | 194 |
| berchn | tree-sitter-python | `add-pep-570-support` | 319df61 | 2021-03-24 | 99.753 | 99.824 | 3,576 | 2,552 | 123 |
| merico-ai | tree-sitter-python | `automatically-sync-from-upstream-repo` | a6fa994 | 2022-09-28 | 99.977 | 99.558 | 327 | 6,400 | 46 |
| ricostynha1 | tree-sitter-myth | `master` | 03cceee | 2025-04-14 | 99.804 | 99.531 | 2,829 | 6,792 | 412 |
| tree-edit | tree-sitter-python | `master` | 197ec32 | 2023-11-14 | 99.693 | 94.335 | 4,206 | 82,031 | 51 |

Not comparable (they build no nodes this harness counts):

- llllvvuu/tree-sitter-python `perf/cache_comment` 0a21d1c: 0 nodes, 4 error files
- llllvvuu/tree-sitter-python `perf/cache_comment_line` cae9dbe: 0 nodes, 4 error files
- loggerhead/tree-sitter-python `master` 484de7d: 0 nodes, 4,911 error files

- No fork fixes the wrong-tree bugs listed above. The best, dokimasia `master` (PEP 696/798/810
  support on top of upstream master), removes 23 wrong and 23 missed nodes (call 9, member 5, spread 9).
- Rows that equal upstream change things these corpora do not exercise (new syntax, queries, scanner
  safety). They are not regressions.
- Older forks lag mostly because they predate upstream fixes, not because of their own changes.
- loggerhead `master` exports `tree_sitter_python` but its root node is `source_file`: a different grammar.
- tree-sitter-sage, tree-sitter-myth and tree-sitter-python-jsx are Python supersets kept under the
  same symbol; they are scored as Python.

## JavaScript

- **Oracle**: the TypeScript compiler's parser, typescript 5.9.3 (pinned in
  `oracles/javascript/package-lock.json`), reading each file as a .js file. It runs as a long-lived
  Node helper (`oracles/javascript/oracle.mjs`). A file is rejected when tsc reports any syntactic
  diagnostic for it as JavaScript, including TypeScript-only syntax.
- **Files**: `.js`/`.mjs`/`.cjs`/`.jsx` in Node.js `lib/` v24.11.1, webpack `lib/` v5.102.1, three.js
  `src/` r181, and [test262](https://github.com/tc39/test262) `test/` (the ECMAScript conformance
  suite). From test262, tests that must fail to parse (`negative: phase: parse`) and module-only tests
  (`flags: [module]`) are skipped: tsc decides module or script from the file, not the test's flags.
  That is 50,324 files.
- **Categories**: binary, unary, await, call, member, subscript, new, ternary, arrow, parenthesized,
  yield, spread: the expression half of the TypeScript harness. Left out on both sides: comma
  expressions, statement-condition parentheses, and JSX. A destructuring *assignment* target
  (`[a, ...b] = x`) is an expression in tsc, so its `rest_pattern` and `assignment_pattern` count as
  spread and binary; binding patterns in declarations and parameters do not count on either side.

### Results (JavaScript)

Measured 2026-11-17. Full numbers per category: `results/javascript-upstream-v0.25.0.json`.

| Build | Commit | Files | Precision % | Recall % | Wrong | Missed | Error files |
|---|---|---|---|---|---|---|---|
| tree-sitter-javascript v0.25.0, real code (node, webpack, three) | 44c892e | 1,632 | 100.000 | 100.000 | 0 | 0 | 0 |
| tree-sitter-javascript v0.25.0, all four corpora | 44c892e | 50,324 | 99.968 | 99.990 | 475 | 153 | 230 |

On ordinary code tree-sitter-javascript matches tsc on every counted node. Every mismatch is in
test262's spec corners and new syntax. Each class below was confirmed by parsing a minimal snippet:

| Input | tree-sitter-javascript reads it as | Nodes |
|---|---|---|
| `for await (let [x] of y)` | `let[x]`: a subscript of a variable named `let` (plain `for (let [x] of y)` is right) | ~250 |
| `var yield = 1; x = yield;` (sloppy mode, `yield` is a name) | a `yield` expression | ~90 |
| `import.source(x)` (source-phase imports) | ERROR, then a call of `source` | ~115 |
| `async function* g() { await (x).next() }` | a call of a function named `await`: the async generator's `await` is missed | ~40 |
| `@C.#x class D {}` (decorator with a private name) | the member expression is missed | ~16 |
| `await using x = r` | an assignment, not a declaration | ~8 |
| `{a: 1}[0]` at statement start (a block, then an array) | a subscript of an object literal | few |

"Nodes" counts wrong + missed nodes in the run, from the `--show` output, rounded.

grammar-orchard's fork, measured 2026-11-24 from its GitHub mirror
(`results/javascript-orchard-2026-11-24.json`), is at the same numbers apart from 2 call nodes:

| Build | Commit | Files | Precision % | Recall % | Wrong | Missed | Error files |
|---|---|---|---|---|---|---|---|
| tree-sitter-javascript-orchard 0.2.0, all four corpora | c1cb253 | 50,324 | 99.969 | 99.990 | 473 | 151 | 226 |

## Prerequisites

- Python 3.14+ and [uv](https://docs.astral.sh/uv/)
- Node 22+ and npm, for the JavaScript oracle
- A C compiler (`cc`) and `git`
- Network access for the first `fetch` (GitHub)

## Reproduce

```sh
uv sync
uv run grammar-accuracy fetch                 # pinned grammars + corpora (all languages) into ~/.cache/grammar-accuracy
(cd oracles/javascript && npm ci)             # the JavaScript oracle
uv run grammar-accuracy run --categories      # about a minute
uv run grammar-accuracy run \
  --build upstream=~/.cache/grammar-accuracy/grammars/upstream-293fdc02038e \
  --build fork=/path/to/tree-sitter-python    # several builds in one pass; ast parses each file once
uv run grammar-accuracy run --show 20 --show-category spread   # print mismatched nodes with source
uv run grammar-accuracy run --lang javascript --categories     # about two minutes
uv run pytest
```

`--build` takes a grammar checkout, its `src/`, or a compiled `.so`. `GRAMMAR_ACCURACY_CACHE`
moves the cache.

## Project Structure

- `src/grammar_accuracy/harness.py`: fetching, compiling grammar builds, scoring, CLI
- `src/grammar_accuracy/python.py`: the Python oracle and category mapping
- `src/grammar_accuracy/javascript.py` + `oracles/javascript/`: the JavaScript mapping and its Node oracle helper
- `pins.json`: pinned grammar and corpus commits
- `results/`: recorded runs
- `tests/`: the harness's own tests

## Related Documentation

- [Technical Reference](TECHNICAL.md): architecture, design decisions, configuration, limitations
- [Usage Guide](USAGE.md): how to read the results

<!-- docvet:anchors
GRAMMAR_ACCURACY_CACHE -> src/grammar_accuracy/harness.py
-->
