import pytest
import tree_sitter

from grammar_accuracy import harness
from grammar_accuracy import javascript as lang


@pytest.fixture(scope='session')
def parser():
    name, g = next(iter(harness.load_pins('javascript')['grammars'].items()))
    path = harness.fetch_repo(g['repo'], g['sha'], harness.grammar_dir(name, g))
    return tree_sitter.Parser(harness.load_language(harness.compile_grammar(path), lang.SYMBOL))


def both(parser, src: str):
    b = src.encode()
    return lang.grammar_nodes(parser.parse(b)), lang.oracle_nodes(b)


AGREE = [
    ('x = a + b * c; y += 1', {'binary'}),
    ('-a; !b; typeof c; void 0; delete o.p; i++', {'unary', 'member'}),
    ('async function f() { await g(); }', {'await', 'call'}),
    ('a.b.c(d)[e]; a?.b?.(); tag`x${y}`', {'member', 'call', 'subscript'}),
    ('new a.B(); new C', {'new', 'member'}),
    ('a ? b : c', {'ternary'}),
    ('const f = (x) => (x)', {'arrow', 'parenthesized'}),
    ('function* g() { yield 1; yield* h; }', {'yield'}),
    ('f(...a); [...b]; ({...c})', {'call', 'spread', 'parenthesized'}),
]


@pytest.mark.parametrize('src,cats', AGREE, ids=[s for s, _ in AGREE])
def test_categories_agree(parser, src, cats):
    mine, theirs = both(parser, src)
    assert mine == theirs
    assert {c for c, *_ in theirs} == cats


@pytest.mark.parametrize('src', [
    'a, b',                                    # comma expressions left out
    'if (a) b; while (c) d;',                  # statement-condition parens
    'const x = <div>{a + b}</div>;',           # JSX left out (the + inside still counts)
    '[a, ...b] = x;',                          # destructuring assignment: rest = spread
    '({a: b = 1, c = 2, ...d} = x);',
    '[a = 1, [b = f()]] = x;',
    'for ([a, ...b] of x);',
    'const [a = 1, ...b] = x; function f([c = 1, ...d]) {}',   # binding patterns: not counted
    'for (const [a, ...b] of x);',
    '[a = (([c = 1]) => c)] = x;',              # an arrow's binding pattern inside a target
])
def test_conventions(parser, src):
    mine, theirs = both(parser, src)
    assert mine == theirs


def test_oracle_rejects():
    assert lang.oracle_nodes(b'let x = ;') is None
    assert lang.oracle_nodes(b'let x: number = 1;') is None    # TypeScript-only syntax
    assert lang.oracle_nodes(b'x = "\xe9"') is None             # not UTF-8


@pytest.mark.parametrize('prefix', ['', '﻿', '// é ü 漢字 😀\n', '"😀"; "é";\r\n'])
def test_offsets_are_bytes(parser, prefix):
    mine, theirs = both(parser, prefix + 'x = "é" + f(a.b)\n')
    assert mine == theirs and len(theirs) == 4


def test_sees_wrong_trees(parser):
    # upstream v0.25.0 reads sloppy-mode `yield` (an identifier there) as a yield expression
    src = 'var yield = 1; x = yield;'
    assert not parser.parse(src.encode()).root_node.has_error
    mine, theirs = both(parser, src)
    assert ('yield', 19, 24) in mine - theirs
