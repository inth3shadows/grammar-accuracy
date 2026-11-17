import pytest
import tree_sitter

from grammar_accuracy import harness
from grammar_accuracy import python as lang


@pytest.fixture(scope='session')
def parser():
    name, g = next(iter(harness.load_pins()['grammars'].items()))
    path = harness.fetch_repo(g['repo'], g['sha'], harness.grammar_dir(name, g))
    return tree_sitter.Parser(harness.load_language(harness.compile_grammar(path), lang.SYMBOL))


def both(parser, src: str):
    b = src.encode()
    return lang.grammar_nodes(parser.parse(b)), lang.oracle_nodes(b)


# One snippet per category that the pinned grammar builds exactly as CPython does.
AGREE = [
    ('a + b * c', {'binary'}),
    ('a and b and c or d', {'boolean'}),
    ('a < b < c', {'compare'}),
    ('-a; not b; ~c', {'unary'}),
    ('async def f():\n    await g()\n', {'await', 'call'}),
    ('a.b.c(d)[e]', {'member', 'call', 'subscript'}),
    ('a if b else c', {'ternary'}),
    ('lambda x: x', {'lambda'}),
    ('(y := 1)', {'walrus'}),
    ('def g():\n    yield 1\n    yield from h\n', {'yield'}),
    ('f(*a, **k)', {'call', 'spread'}),
    ('[x for x in y]; {x for x in y}; {k: v for k, v in y}; f(x for x in y)', {'comprehension', 'call'}),
    ('a[1:2]; a[::3]', {'subscript', 'slice'}),
    ('x: list[int] | None = None', {'subscript', 'binary'}),
    ('x: a.B', {'member'}),
]


@pytest.mark.parametrize('src,cats', AGREE, ids=[s for s, _ in AGREE])
def test_categories_agree(parser, src, cats):
    mine, theirs = both(parser, src)
    assert mine == theirs
    assert {c for c, *_ in theirs} == cats


@pytest.mark.parametrize('src', [
    '(a)',                                   # parentheses have no ast node
    '{**d}',                                 # dict-literal splat has no ast node
    'def f(*a, **k): pass',                  # vararg is an arg, not a Starred
    'def f(*a: int, **k: int): pass',
    'lambda *a: 0',
    'match x:\n    case [*rest] if rest:\n        pass\n',   # patterns skipped, guard counted
    "f'{a}' 'b' f'{c!r:>{w}}'",               # string nodes skipped
    'return_ = 1, 2; x[a, b]',               # tuples not counted
    'class A[T: int, *Ts, **P]: pass',        # PEP 695 declarations skipped, bounds too
    'def f[T: (a.b, c)](x: T) -> T: pass',
    'type X[*Ts] = tuple[*Ts]',
])
def test_conventions_left_out(parser, src):
    mine, theirs = both(parser, src)
    assert mine == theirs


def test_match_guard_is_counted(parser):
    mine, theirs = both(parser, 'match x:\n    case [*rest] if f(rest):\n        pass\n')
    assert {c for c, *_ in theirs} == {'call'}
    assert mine == theirs


@pytest.mark.parametrize('prefix', ['', '\ufeff', '# é ü 漢字\n', 's = "漢字"; t = 1\r\n', 'a = 1\rb = 2\r'])
def test_offsets_are_bytes(parser, prefix):
    mine, theirs = both(parser, prefix + 'x = "é" + f(a.b)\n')
    assert mine == theirs and len(theirs) == 3


def test_oracle_rejects():
    assert lang.oracle_nodes(b'def (:\n') is None
    assert lang.oracle_nodes('# -*- coding: latin-1 -*-\nx = "\xe9"\n'.encode('latin-1')) is None


def test_sees_wrong_trees(parser):
    # upstream v0.25.0 reads `[*a.b()]` as `(*a).b()`: no ERROR, wrong tree. The harness must see it.
    src = '[*a.b()]'
    tree = parser.parse(src.encode())
    assert not tree.root_node.has_error
    mine, theirs = both(parser, src)
    assert mine != theirs
    assert ('spread', 1, 7) in theirs - mine


def test_score_arithmetic():
    s = harness.Score()
    s.add({('call', 0, 3), ('member', 0, 1)}, {('call', 0, 3), ('member', 1, 2), ('unary', 0, 1)})
    t = s.totals()
    assert (t['grammar_nodes'], t['oracle_nodes'], t['matched'], t['wrong'], t['missed']) == (2, 3, 1, 1, 2)
    assert t['precision'] == 0.5 and t['recall'] == pytest.approx(1 / 3)
    assert s.by_category()['member'] == {'wrong': 1, 'missed': 1, 'oracle': 1}
