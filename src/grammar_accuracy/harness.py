"""Fetch pinned grammars and corpora, compile grammar builds, and score them against the oracle."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter

from . import javascript, python

LANGS = {'python': python, 'javascript': javascript}

ROOT = Path(__file__).resolve().parents[2]
PINS = ROOT / 'pins.json'


def cache_root() -> Path:
    return Path(os.environ.get('GRAMMAR_ACCURACY_CACHE', Path.home() / '.cache' / 'grammar-accuracy'))


def load_pins(language: str) -> dict:
    return json.loads(PINS.read_text())[language]


def fetch_repo(repo: str, sha: str, dest: Path) -> Path:
    """Shallow-fetch one commit of a GitHub repo into dest (idempotent)."""
    marker = dest / '.fetched'
    if marker.exists() and marker.read_text().strip() == sha:
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    git = ['git', '-C', str(dest)]
    subprocess.run([*git, 'init', '-q'], check=True)
    subprocess.run([*git, 'fetch', '-q', '--depth', '1', f'https://github.com/{repo}.git', sha], check=True)
    subprocess.run([*git, 'checkout', '-q', '--force', 'FETCH_HEAD'], check=True)
    head = subprocess.run([*git, 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
    if head != sha:
        raise SystemExit(f'{repo}: fetched {head}, pinned {sha}')
    marker.write_text(sha + '\n')
    return dest


def corpus_dir(c: dict) -> Path:
    return cache_root() / 'corpora' / f"{c['name']}-{c['sha'][:12]}"


def grammar_dir(name: str, g: dict) -> Path:
    return cache_root() / 'grammars' / f"{name}-{g['sha'][:12]}"


# --- grammar builds ---------------------------------------------------------------------------

def _src_dir(path: Path) -> Path:
    for cand in (path, path / 'src'):
        if (cand / 'parser.c').is_file():
            return cand
    raise SystemExit(f'{path}: no parser.c in it or in its src/')


def compile_grammar(path: Path) -> Path:
    """Compile a grammar checkout's committed parser.c (+ scanner.c, or an older grammar's C++
    scanner.cc) to a cached shared library."""
    src = _src_dir(path)
    sources = [src / 'parser.c'] + [p for p in (src / 'scanner.c', src / 'scanner.cc') if p.is_file()]
    h = hashlib.sha256()
    for p in sources:
        h.update(p.name.encode() + b'\0' + p.read_bytes())
    out = cache_root() / 'builds' / f'{h.hexdigest()[:16]}.so'
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(f'.{os.getpid()}.tmp')
        cxx = any(p.suffix == '.cc' for p in sources)
        # the C++ driver links libstdc++; -x keeps parser.c compiled as C
        files = [a for p in sources for a in ('-x', 'c++' if p.suffix == '.cc' else 'c', str(p))]
        subprocess.run(['c++' if cxx else 'cc', '-O2', '-shared', '-fPIC', '-I', str(src), *files, '-o', str(tmp)],
                       check=True)
        tmp.replace(out)
    return out


_PyCapsule_New = ctypes.pythonapi.PyCapsule_New
_PyCapsule_New.restype = ctypes.py_object
_PyCapsule_New.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]


def load_language(so: Path, symbol: str) -> tree_sitter.Language:
    fn = getattr(ctypes.CDLL(str(so)), symbol)
    fn.restype = ctypes.c_void_p
    return tree_sitter.Language(_PyCapsule_New(fn(), b'tree_sitter.Language', None))


def resolve_build(spec: str) -> tuple[str, Path]:
    """NAME=PATH, where PATH is a grammar checkout (or its src/) or a compiled .so."""
    name, sep, path = spec.partition('=')
    if not sep or not name or not path:
        raise SystemExit('--build takes NAME=PATH')
    p = Path(path).expanduser()
    return name, p if p.suffix == '.so' else compile_grammar(p)


# --- scoring ----------------------------------------------------------------------------------

@dataclass
class Score:
    grammar: Counter = field(default_factory=Counter)  # category -> nodes the grammar emits
    oracle: Counter = field(default_factory=Counter)   # category -> nodes the oracle emits
    matched: Counter = field(default_factory=Counter)
    error_files: list[str] = field(default_factory=list)

    def add(self, mine: set, theirs: set) -> None:
        for cat, *_ in mine:
            self.grammar[cat] += 1
        for cat, *_ in theirs:
            self.oracle[cat] += 1
        for cat, *_ in mine & theirs:
            self.matched[cat] += 1

    def totals(self) -> dict:
        g, o, m = (sum(c.values()) for c in (self.grammar, self.oracle, self.matched))
        return {
            'grammar_nodes': g, 'oracle_nodes': o, 'matched': m,
            'wrong': g - m, 'missed': o - m,
            'precision': m / g if g else None, 'recall': m / o if o else None,
            'error_files': len(self.error_files),
        }

    def by_category(self) -> dict:
        cats = sorted(set(self.grammar) | set(self.oracle))
        return {c: {'wrong': self.grammar[c] - self.matched[c], 'missed': self.oracle[c] - self.matched[c],
                    'oracle': self.oracle[c]} for c in cats}


def list_files(base: Path, exts: frozenset[str]) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if d not in ('.git', 'node_modules'))
        out.extend(Path(dirpath, f) for f in filenames if Path(f).suffix in exts)
    return sorted(p for p in out if p.is_file() and not p.is_symlink())


def _pct(x: float | None) -> str:
    return '-' if x is None else f'{100 * x:.3f}'


def _snippet(src: bytes, start: int, end: int, width: int = 80) -> str:
    s = src[start:end].decode('utf-8', 'replace').replace('\n', '\\n')
    return s if len(s) <= width else s[:width - 3] + '...'


def run(args: argparse.Namespace) -> int:
    lang = LANGS[args.lang]
    pins = load_pins(args.lang)
    specs = args.build or [f'{n}={grammar_dir(n, g)}' for n, g in pins['grammars'].items()]
    builds = []
    for spec in specs:
        name, so = resolve_build(spec)
        builds.append((name, tree_sitter.Parser(load_language(so, lang.SYMBOL))))
    corpora = [c for c in pins['corpora'] if not args.corpus or c['name'] in args.corpus]
    if args.corpus and len(corpora) != len(set(args.corpus)):
        raise SystemExit(f'unknown corpus in {args.corpus}')

    scores = {name: Score() for name, _ in builds}
    files = rejected = skipped = 0
    shown = Counter()
    t0 = time.monotonic()
    for c in corpora:
        base = corpus_dir(c)
        if not (base / '.fetched').exists():
            raise SystemExit(f"corpus {c['name']} is not fetched; run `grammar-accuracy fetch`")
        root = base / c['subdir'] if c['subdir'] else base
        paths = list_files(root, lang.EXTS)
        # a corpus can exclude files by content, e.g. test262's tests that must fail to parse
        skip = re.compile(c['skip_if'].encode()) if c.get('skip_if') else None
        if not paths:
            raise SystemExit(f"corpus {c['name']}: 0 files under {root}")
        for p in paths:
            src = p.read_bytes()
            if skip and skip.search(src):
                skipped += 1
                continue
            theirs = lang.oracle_nodes(src)
            if theirs is None:
                rejected += 1
                continue
            files += 1
            rel = f"{c['name']}:{p.relative_to(root)}"
            for name, parser in builds:
                tree = parser.parse(src)
                mine = lang.grammar_nodes(tree)
                scores[name].add(mine, theirs)
                if tree.root_node.has_error:
                    scores[name].error_files.append(rel)
                if args.show and name == builds[0][0]:
                    for kind, diff in (('wrong', mine - theirs), ('missed', theirs - mine)):
                        for cat, s, e in sorted(diff, key=lambda x: x[1]):
                            if (args.show_category in (None, cat)) and shown[kind] < args.show:
                                shown[kind] += 1
                                line = src.count(b'\n', 0, s) + 1
                                print(f'{kind:6} {cat:13} {rel}:{line}  {_snippet(src, s, e)}')
    if files == 0:
        raise SystemExit('oracle accepted 0 files: is it blind?')

    print(f'{files} files accepted by {lang.oracle_name()} ({rejected} rejected or not UTF-8, {skipped} skipped by corpus rule), '
          f'{time.monotonic() - t0:.0f}s')
    print(f"{'build':<16} {'precision %':>11} {'recall %':>9} {'wrong':>7} {'missed':>7} {'error files':>11}")
    for name, _ in builds:
        t = scores[name].totals()
        print(f"{name:<16} {_pct(t['precision']):>11} {_pct(t['recall']):>9} {t['wrong']:>7} {t['missed']:>7} {t['error_files']:>11}")
    if args.categories:
        for name, _ in builds:
            print(f'\n{name}: wrong / missed / oracle nodes')
            for cat, v in scores[name].by_category().items():
                print(f"  {cat:<14} {v['wrong']:>6} {v['missed']:>6} {v['oracle']:>9}")
    if args.json:
        out = {
            'language': args.lang,
            'oracle': lang.oracle_name(),
            'files': files, 'rejected': rejected, 'skipped': skipped,
            'corpora': {c['name']: c['sha'] for c in corpora},
            'builds': {n: {**scores[n].totals(), 'categories': scores[n].by_category(),
                           'error_file_list': scores[n].error_files} for n, _ in builds},
        }
        Path(args.json).write_text(json.dumps(out, indent=2) + '\n')
    return 0


def fetch(args: argparse.Namespace) -> int:
    for language in args.lang or LANGS:
        _fetch(load_pins(language))
    return 0


def _fetch(pins: dict) -> None:
    for name, g in pins['grammars'].items():
        print(f"grammar {name}: {g['repo']}@{g['ref']}")
        fetch_repo(g['repo'], g['sha'], grammar_dir(name, g))
    for c in pins['corpora']:
        print(f"corpus {c['name']}: {c['repo']}@{c['ref']}")
        fetch_repo(c['repo'], c['sha'], corpus_dir(c))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog='grammar-accuracy', description=__doc__)
    sub = ap.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('fetch', help='fetch the pinned grammars and corpora into the cache')
    f.add_argument('--lang', action='append', choices=LANGS, help='only this language (repeatable; default: all)')
    f.set_defaults(fn=fetch)
    r = sub.add_parser('run', help='score grammar builds against the oracle')
    r.add_argument('--lang', choices=LANGS, default='python', help='language (default: python)')
    r.add_argument('--build', action='append', metavar='NAME=PATH',
                   help='grammar checkout, its src/, or a compiled .so (repeatable; default: pinned upstream)')
    r.add_argument('--corpus', action='append', help='limit to this corpus (repeatable)')
    r.add_argument('--json', help='write full results here')
    r.add_argument('--categories', action='store_true', help='print wrong/missed per category')
    r.add_argument('--show', type=int, default=0, metavar='N', help='print up to N wrong and N missed nodes (first build)')
    r.add_argument('--show-category', help='limit --show to one category')
    r.set_defaults(fn=run)
    args = ap.parse_args(argv)
    return args.fn(args)
