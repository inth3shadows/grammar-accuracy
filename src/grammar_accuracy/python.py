"""Python: tree-sitter-python's expression nodes against CPython's own parser (`ast.parse`).

A node is `(category, start_byte, end_byte)`. Both sides map their node kinds to shared
categories; spans are byte offsets into the file on both sides (ast's `col_offset` is a UTF-8
byte offset into its line, so files must be UTF-8).

Conventions the grammar cannot change are left out on both sides:
- parentheses: ast has no node for them, so `parenthesized_expression` is not counted;
- `a and b and c` is one flat BoolOp in ast: only the outermost `boolean_operator` of a
  same-operator chain counts;
- `**d` in a dict literal has no ast node: `dictionary_splat` counts only in call arguments;
- `*args` in a parameter list is an `arg` in ast, not a Starred;
- match-statement patterns (a separate node family on both sides) are skipped;
- string nodes (f-strings, concatenation) are not counted, but expressions inside them are;
- tuples are not counted: `x[a, b]` and `return a, b` have a Tuple in ast and none, or an
  `expression_list`, here;
- PEP 695 type-parameter declarations (`class A[T: int, *Ts]`, the `X[T]` of `type X[T] = ...`)
  are type_param nodes in ast and types here: skipped, bounds included.
"""

from __future__ import annotations

import ast
import re
import warnings

EXTS = frozenset({'.py'})
SYMBOL = 'tree_sitter_python'

ORACLE = {
    ast.BinOp: 'binary',
    ast.BoolOp: 'boolean',
    ast.Compare: 'compare',
    ast.UnaryOp: 'unary',
    ast.Await: 'await',
    ast.Call: 'call',
    ast.Attribute: 'member',
    ast.Subscript: 'subscript',
    ast.IfExp: 'ternary',
    ast.Lambda: 'lambda',
    ast.NamedExpr: 'walrus',
    ast.Yield: 'yield', ast.YieldFrom: 'yield',
    ast.Starred: 'spread',
    ast.ListComp: 'comprehension', ast.SetComp: 'comprehension',
    ast.DictComp: 'comprehension', ast.GeneratorExp: 'comprehension',
    ast.Slice: 'slice',
}

GRAMMAR = {
    'binary_operator': 'binary', 'union_type': 'binary',
    'boolean_operator': 'boolean',
    'comparison_operator': 'compare',
    'unary_operator': 'unary', 'not_operator': 'unary',
    'await': 'await',
    'call': 'call',
    'attribute': 'member', 'member_type': 'member',
    'subscript': 'subscript', 'generic_type': 'subscript',
    'conditional_expression': 'ternary',
    'lambda': 'lambda',
    'named_expression': 'walrus',
    'yield': 'yield',
    'list_splat': 'spread', 'list_splat_pattern': 'spread', 'splat_type': 'spread',
    'dictionary_splat': 'spread',
    'list_comprehension': 'comprehension', 'set_comprehension': 'comprehension',
    'dictionary_comprehension': 'comprehension', 'generator_expression': 'comprehension',
    'slice': 'slice',
}
GRAMMAR_SKIP = frozenset({'case_pattern'})
# node type -> field holding a PEP 695 type-parameter declaration
TYPE_PARAM_DECL = {'class_definition': 'type_parameters', 'function_definition': 'type_parameters',
                   'type_alias_statement': 'left'}
PARAM_LISTS = frozenset({'parameters', 'lambda_parameters', 'typed_parameter'})

_LINE_END = re.compile(rb'\r\n|\r|\n')
BOM = b'\xef\xbb\xbf'


def line_starts(source: bytes) -> list[int]:
    """Byte offset of each line start, splitting the way CPython's tokenizer does."""
    return [0] + [m.end() for m in _LINE_END.finditer(source)]


def oracle_nodes(source: bytes) -> set[tuple[str, int, int]] | None:
    """The nodes CPython's parser builds, or None if it rejects the file or it is not UTF-8."""
    try:
        source.decode('utf-8')
    except UnicodeDecodeError:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    starts = line_starts(source)
    # ast columns on line 1 do not count a BOM; tree-sitter's bytes do
    bom = len(BOM) if source.startswith(BOM) else 0

    def offset(line: int, col: int) -> int:
        return starts[line - 1] + col + (bom if line == 1 else 0)

    out: set[tuple[str, int, int]] = set()
    stack: list[ast.AST] = [tree]
    while stack:
        n = stack.pop()
        if isinstance(n, ast.match_case):
            # the pattern is skipped; the guard and body are ordinary code
            stack.extend(x for x in (n.guard, *n.body) if x is not None)
            continue
        if isinstance(n, ast.type_param):
            continue
        cat = ORACLE.get(type(n))
        if isinstance(n, ast.keyword) and n.arg is None:
            cat = 'spread'  # `**k` in a call
        if cat:
            out.add((cat, offset(n.lineno, n.col_offset), offset(n.end_lineno, n.end_col_offset)))
        stack.extend(ast.iter_child_nodes(n))
    return out


def grammar_nodes(tree) -> set[tuple[str, int, int]]:
    """The nodes a tree-sitter-python build makes."""
    out: set[tuple[str, int, int]] = set()
    stack = [(tree.root_node, None, None)]  # (node, parent type, parent boolean operator)
    while stack:
        n, ptype, pop = stack.pop()
        t = n.type
        if t in GRAMMAR_SKIP:
            continue
        decl = n.child_by_field_name(TYPE_PARAM_DECL[t]) if t in TYPE_PARAM_DECL else None
        cat = GRAMMAR.get(t)
        op = None
        if t == 'boolean_operator':
            o = n.child_by_field_name('operator')
            op = o.type if o is not None else None
            if ptype == 'boolean_operator' and pop == op:
                cat = None  # inner link of a flat chain
        elif t == 'dictionary_splat' and ptype != 'argument_list':
            cat = None
        elif t == 'list_splat_pattern' and ptype in PARAM_LISTS:
            cat = None
        if cat:
            out.add((cat, n.start_byte, n.end_byte))
        stack.extend((c, t, op) for c in n.named_children if c != decl)
    return out
