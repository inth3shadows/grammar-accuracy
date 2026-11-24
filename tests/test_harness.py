import subprocess

import pytest
import tree_sitter

from grammar_accuracy import harness
from grammar_accuracy import python as lang


@pytest.fixture(scope='session')
def upstream_src():
    name, g = next(iter(harness.load_pins('python')['grammars'].items()))
    return harness.fetch_repo(g['repo'], g['sha'], harness.grammar_dir(name, g)) / 'src'


def _build(src, out, *defines):
    subprocess.run(['cc', '-O2', '-shared', '-fPIC', *defines, '-I', str(src),
                    str(src / 'parser.c'), str(src / 'scanner.c'), '-o', str(out)], check=True)
    return out


def test_loads_orchard_symbol(upstream_src, tmp_path):
    # grammar-orchard builds export tree_sitter_python_orchard, not tree_sitter_python
    so = _build(upstream_src, tmp_path / 'orchard.so', '-Dtree_sitter_python=tree_sitter_python_orchard')
    tree = tree_sitter.Parser(harness.load_language(so, lang.SYMBOL)).parse(b'a + b')
    assert str(tree.root_node).startswith('(module')


def test_missing_symbol_names_both(upstream_src, tmp_path):
    so = _build(upstream_src, tmp_path / 'other.so', '-Dtree_sitter_python=tree_sitter_other')
    with pytest.raises(SystemExit, match='tree_sitter_python, tree_sitter_python_orchard'):
        harness.load_language(so, lang.SYMBOL)


def test_untracked_generated_files_hint(tmp_path):
    (tmp_path / 'grammar.js').write_text('')
    with pytest.raises(SystemExit, match='tree-sitter generate'):
        harness.compile_grammar(tmp_path)
