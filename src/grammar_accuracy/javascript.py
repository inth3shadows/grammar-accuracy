"""JavaScript: tree-sitter-javascript's expression nodes against the TypeScript compiler's parser.

The oracle is `ts.createSourceFile` over the file as a .js file (typescript pinned in
`oracles/javascript/package-lock.json`), run as a long-lived Node helper. A file is rejected
when tsc reports any syntactic diagnostic for it as JavaScript, including TypeScript-only syntax.

Categories and conventions follow tree-sitter-typescript's `scripts/tree-accuracy.mjs`:
- comma expressions are left out (`sequence_expression` nests the other way);
- statement conditions, `if (x)`, are parenthesized here and bare in tsc;
- JSX is left out on both sides;
- a destructuring *assignment* target (`[a, ...b] = x`, `({a: b = 1} = x)`) is an expression in
  tsc: its rest elements are spreads and its defaults are `=` binaries. Here they are
  `rest_pattern` and `assignment_pattern`, and count as spread and binary only inside such a
  target (not in declarations or parameters, which tsc builds as binding patterns).
"""

from __future__ import annotations

import atexit
import json
import shutil
import subprocess
from pathlib import Path

EXTS = frozenset({'.js', '.mjs', '.cjs', '.jsx'})
SYMBOL = 'tree_sitter_javascript'
ORACLE_DIR = Path(__file__).resolve().parents[2] / 'oracles' / 'javascript'

GRAMMAR = {
    'binary_expression': 'binary', 'assignment_expression': 'binary', 'augmented_assignment_expression': 'binary',
    'unary_expression': 'unary', 'update_expression': 'unary',
    'await_expression': 'await',
    'member_expression': 'member',
    'subscript_expression': 'subscript',
    'call_expression': 'call',
    'new_expression': 'new',
    'ternary_expression': 'ternary',
    'arrow_function': 'arrow',
    'parenthesized_expression': 'parenthesized',
    'yield_expression': 'yield',
    'spread_element': 'spread',
}
GRAMMAR_SKIP = frozenset({'jsx_element', 'jsx_self_closing_element'})
PATTERNS = frozenset({'array_pattern', 'object_pattern', 'pair_pattern', 'assignment_pattern', 'rest_pattern',
                      'object_assignment_pattern'})
ASSIGN_TARGET = {'rest_pattern': 'spread', 'assignment_pattern': 'binary'}
COND_PARENTS = frozenset({'if_statement', 'while_statement', 'do_statement', 'switch_statement', 'with_statement'})


class _Oracle:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None

    def start(self) -> subprocess.Popen:
        if self.proc is None:
            if not (ORACLE_DIR / 'node_modules' / 'typescript').is_dir():
                raise SystemExit(f'JavaScript oracle not installed: run `npm ci` in {ORACLE_DIR}')
            node = shutil.which('node') or 'node'
            self.proc = subprocess.Popen([node, str(ORACLE_DIR / 'oracle.mjs')], stdin=subprocess.PIPE,
                                         stdout=subprocess.PIPE, text=True, encoding='utf-8')
            atexit.register(self.stop)
        return self.proc

    def ask(self, text: str) -> dict:
        p = self.start()
        p.stdin.write(json.dumps({'src': text}) + '\n')
        p.stdin.flush()
        line = p.stdout.readline()
        if not line:
            raise SystemExit(f'JavaScript oracle exited (code {p.poll()})')
        return json.loads(line)

    def version(self) -> str:
        lock = json.loads((ORACLE_DIR / 'package-lock.json').read_text())
        return lock['packages']['node_modules/typescript']['version']

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
            self.proc = None


_oracle = _Oracle()


def oracle_name() -> str:
    return f'typescript {_oracle.version()} createSourceFile (.js)'


def oracle_nodes(source: bytes) -> set[tuple[str, int, int]] | None:
    """The nodes tsc builds for the file as JavaScript, or None if it rejects it or it is not UTF-8."""
    try:
        text = source.decode('utf-8')
    except UnicodeDecodeError:
        return None
    reply = _oracle.ask(text)
    if 'nodes' not in reply:
        return None
    return {(c, s, e) for c, s, e in reply['nodes']}


def grammar_nodes(tree) -> set[tuple[str, int, int]]:
    """The nodes a tree-sitter-javascript build makes."""
    out: set[tuple[str, int, int]] = set()
    stack = [(tree.root_node, None, False)]  # (node, parent type, inside a destructuring assignment target)
    while stack:
        n, ptype, target = stack.pop()
        t = n.type
        if t in GRAMMAR_SKIP:
            continue
        target = target and t in PATTERNS
        cat = ASSIGN_TARGET.get(t) if target else GRAMMAR.get(t)
        if t == 'parenthesized_expression' and ptype in COND_PARENTS:
            cat = None
        if cat:
            out.add((cat, n.start_byte, n.end_byte))
        left = None
        if t == 'assignment_expression' or (t == 'for_in_statement' and n.child_by_field_name('kind') is None):
            left = n.child_by_field_name('left')
        stack.extend((c, t, target or c == left) for c in n.named_children)
    return out
