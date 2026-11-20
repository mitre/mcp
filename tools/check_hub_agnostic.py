#!/usr/bin/env python3
"""Report where the MCP hub (the ``mcp`` plugin) references a SPECIFIC other plugin.

The hub's contract: the ``mcp`` plugin contains ZERO references
scoped to a specific OTHER plugin. It discovers and drives plugins generically,
through the server, workflow and capability registries built at boot and the
MCP tools those servers expose. This gate catches the common spellings of a
coupling (listed below), including shapes a literal grep misses, so that a new
``import plugins.<other>...`` or ``plugins/<other>/...`` read is flagged before
it lands in the hub.

WHAT IT CATCHES: this is a tripwire for the common ways of spelling a coupling,
not a proof that the hub is plugin-agnostic. A plugin name is letters, digits,
``_`` and ``-``; any name except the hub's own (``mcp``) counts, so the gate
works the same in a standalone checkout of this plugin and inside a Caldera
tree. Python is parsed with ``ast`` (comments and docstrings are not code; a
``#`` inside a string cannot hide the rest of the line):
  - ``import plugins.<x>``, ``from plugins.<x>... import``, ``from plugins import <x>``
  - a string literal containing ``plugins.<x>`` (``importlib.import_module``),
    ``plugins/<x>`` (with or without a trailing slash) or ``/plugin/<x>``
  - a join onto ``"plugins"``: ``os.path.join(..., "plugins", "<x>")``,
    ``Path(..., "plugins", "<x>")``, ``Path("plugins") / "<x>"``,
    ``root / "plugins" / "<x>"``, or ``<name> / "<x>"`` where the variable or
    attribute is named like the plugins dir (``PLUGINS_DIR``, ``plugins_root``)
In ``.vue``, ``.js``, ``.mjs``, ``.ts``, ``.tsx`` and ``.html`` files the code
text (``//`` lines and ``/* */`` / ``<!-- -->`` blocks that open a line are
skipped) is searched for ``plugins/<x>`` and ``/plugin/<x>``.
Inside a Caldera tree it also flags ``<..._dir|_root|_path|parent> / "<x>"``
when ``<x>`` is a sibling plugin found under ``plugins/`` (a directory with a
``hook.py``, backup/snapshot dirs skipped); standalone that one form is not
checked, and the output says so.

NOT DETECTED: names computed or concatenated at run time
(``'/plugin/' + name``, f-strings), relative-path imports or paths that climb
out of this plugin (``../../<x>/...``), and a join onto an arbitrary variable
that is not named like the plugins dir (``base_dir / "<x>"``,
``parent.parent / "<x>"``) unless ``<x>`` is a discovered sibling.

SCOPE: ``.py``, ``.vue``, ``.js``, ``.mjs``, ``.ts``, ``.tsx`` and ``.html``
files under ``app/``, ``gui/``, ``templates/`` and ``static/``, plus the
top-level ``.py`` files. Only generated or third-party trees are skipped
(``node_modules``, ``dist``, ``__pycache__``, ``.git``), matched below the plugin
root, never against the directories the checkout itself lives in. A file that
cannot be read or parsed is reported and fails ``--strict``, as does a run that
scans no file at all.

CATEGORIES (each hit is tagged):
  import-other-plugin    [GATE] an import of another plugin's Python, or its
                         dotted module name in a string.
  path-read-other-plugin [GATE] a path into another plugin's dir (the literal and
                         join forms above). Reach the data through that plugin's
                         interface (service / MCP tool / REST route), not off its
                         files.
  rest-mount-other-plugin [GATE] a literal ``/plugin/<other>`` HTTP mount.
                         Resolve it from the discovered server metadata or call
                         that plugin's MCP tools instead.
  noncore-service-lookup [warn] ``services.get("X_svc")`` for a non-core service -
                         locate the service by CAPABILITY (duck-typed interface,
                         e.g. ``hasattr(svc, "run_check")``), not its
                         plugin-specific name key.

Plugin-NAME literals (``name == "pluginx"`` etc.) are intentionally NOT scanned:
a generic "quoted string == a plugin dir name" scan is unusable noise (dirs named
access/response/atomic/human collide with ordinary words).

GATE vs warn: import/path-read/rest-mount are unambiguous and GATE under ``--strict``.
noncore-service-lookup is advisory (reported, never gating).

BASELINE: ``--strict`` fails only on GATING findings NOT present in the baseline
file (``tools/hub_agnostic_baseline.txt``), so existing debt is burned down
without blocking the pipeline while NO new coupling can land. Regenerate with
``--update-baseline`` after a fix (it rewrites the baseline from the current
gating findings, dropping the ones you removed). An inline
``hub-agnostic-ok: <reason>`` comment (``#`` or ``//``) on a line suppresses that
line entirely.

Exit: 0, unless ``--strict`` and there is a NEW (non-baselined) gating finding,
an unreadable file, or no file scanned → 1.

Usage:
    python tools/check_hub_agnostic.py [paths...] [--strict] [--quiet] [--update-baseline]
No paths → scans the hub plugin's own source (app/, mcp/, gui/, templates/,
static/, top-level *.py).
"""
from __future__ import annotations

import argparse
import ast
import os
import re
from collections import Counter
from pathlib import Path

_HUB_NAME = 'mcp'
_JS_SUFFIXES = ('.vue', '.js', '.mjs', '.ts', '.tsx', '.html')
_SOURCE_SUFFIXES = ('.py',) + _JS_SUFFIXES
_EXCLUDE_DIRS = frozenset({'node_modules', 'dist', '__pycache__', '.git'})
_CONVENTIONAL_DIRS = ('app', 'mcp', 'gui', 'templates', 'static')
_SUPPRESS_MARKER = 'hub-agnostic-ok'
_BACKUP_RE = re.compile(
    r'backup|snapshot|~$|[-_.](old|orig|copy|bak)(\b|$)|\d{4}-\d{2}-\d{2}',
    re.IGNORECASE)

# Services owned by caldera-core or the hub itself, looking these up by name is
# NOT a plugin coupling. Anything else ending in ``_svc`` is flagged (advisory).
_CORE_SERVICES = frozenset({
    'data_svc', 'file_svc', 'app_svc', 'rest_svc', 'auth_svc', 'contact_svc',
    'event_svc', 'knowledge_svc', 'learning_svc', 'planning_svc', 'rest_api',
    'config', 'mcp_svc',
})

_GATING = ('import-other-plugin', 'path-read-other-plugin', 'rest-mount-other-plugin')
_CATEGORY_ORDER = ('import-other-plugin', 'path-read-other-plugin',
                   'rest-mount-other-plugin', 'noncore-service-lookup')
_BASELINE_NAME = 'hub_agnostic_baseline.txt'

_HINTS = {
    'import-other-plugin':
        'the hub imports another plugin\'s Python; reach it through a service '
        'located by capability or its MCP tool, never an import',
    'path-read-other-plugin':
        'the hub reads another plugin\'s files/layout; get the data from that '
        'plugin\'s interface (service / MCP tool / REST route), not off disk',
    'rest-mount-other-plugin':
        'the hub hardcodes another plugin\'s HTTP mount (/plugin/<name>/...); '
        'resolve the mount/base from the discovered server metadata or call '
        'that plugin\'s MCP tools, not a literal URL path',
    'noncore-service-lookup':
        'a non-core service looked up by name; locate it by duck-typed '
        'capability (e.g. hasattr(svc, "run_check")), not the name key',
}


def _hub_root() -> Path:
    return Path(__file__).resolve().parents[1]


def discover_other_plugins() -> set[str]:
    """Every installed plugin except the hub itself (a dir shipping hook.py)."""
    pdir = _hub_root().parent
    names: set[str] = set()
    if not pdir.is_dir():
        return names
    for child in pdir.iterdir():
        if not child.is_dir() or child.name == _HUB_NAME:
            continue
        if _BACKUP_RE.search(child.name):
            continue
        if (child / 'hook.py').exists():
            names.add(child.name)
    return names


def _relpath(f: Path, hub_root: Path, base: Path) -> Path:
    """``f`` relative to the plugin root, else to ``base`` (the scan target), else as given."""
    for root in (hub_root, base):
        for cand in (Path(os.path.abspath(f)), f.resolve()):
            try:
                return cand.relative_to(root.resolve())
            except ValueError:
                continue
    return f


def _iter_files(paths: list[Path], hub_root: Path) -> tuple[list[tuple[Path, Path]], list[str]]:
    """Takes scan targets, produces ([(file, its relpath)], [targets that do not exist]).

    Excluded directories are matched on the path BELOW the plugin root (or below
    the target, for a target outside it), so a checkout that happens to live
    under e.g. ``.../build/`` or ``.../tools/`` is still scanned.
    """
    out: list[tuple[Path, Path]] = []
    missing: list[str] = []
    for p in paths:
        if p.is_file():
            if p.suffix in _SOURCE_SUFFIXES:
                out.append((p, _relpath(p, hub_root, p.parent)))
        elif p.is_dir():
            for f in sorted(p.rglob('*')):
                if f.suffix not in _SOURCE_SUFFIXES:
                    continue
                rel = _relpath(f, hub_root, p)
                if any(part in _EXCLUDE_DIRS for part in rel.parts[:-1]):
                    continue
                out.append((f, rel))
        else:
            missing.append(str(p))
    return out, missing


def _default_scan_targets() -> list[Path]:
    root = _hub_root()
    targets = [root / d for d in _CONVENTIONAL_DIRS if (root / d).is_dir()]
    targets += list(root.glob('*.py'))
    return targets or [root]


class Finding:
    __slots__ = ('category', 'hint', 'line', 'lineno', 'relpath', 'subtype', 'token')

    def __init__(self, category, subtype, relpath, lineno, token, line, hint):
        self.category, self.subtype, self.relpath = category, subtype, relpath
        self.lineno, self.token, self.line, self.hint = lineno, token, line, hint

    def key(self) -> str:
        """Baseline key, line-number-independent so edits don't churn it."""
        return f'{self.category}|{self.relpath}|{self.subtype}|{self.token}'


_NAME = r'(\w[\w-]*)'  # a plugin dir name: letters, digits, _ and -
# Searched in Python string literals and in .vue/.js/... code text.
_PATH_LITERAL_RE = re.compile(r'(?<![\w-])plugins/' + _NAME)
_REST_MOUNT_RE = re.compile(r'/plugin/' + _NAME)
# Python string literals only (in JS, ``plugins.map(...)`` is ordinary code).
_MODULE_STRING_RE = re.compile(r'(?<![\w.])plugins\.([A-Za-z_]\w*)')
# A variable or attribute named like the plugins dir (PLUGINS_DIR, plugins_root),
# and the receivers of the generic join checked against discovered plugins.
_PLUGINS_DIR_NAME_RE = re.compile(r'(?:^|_)plugins(?:_|$)', re.IGNORECASE)
_DIR_NAME_RE = re.compile(r'(?:dir|root|path)$|^parent$', re.IGNORECASE)


def _str(node):
    """The value of a str literal node, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _ident(node):
    """The variable or attribute name a node is spelled with, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _ends_in_plugins(value) -> bool:
    """True for a path string whose last segment is ``plugins``."""
    return value is not None and value.rstrip('/').rsplit('/', 1)[-1] == 'plugins'


def _first_segment(value: str) -> str:
    return value.strip('/').split('/', 1)[0]


def _plugins_dir_spelling(node):
    """Takes the left side of a ``/`` join, produces the subtype if it spells the plugins dir, else None."""
    if _ends_in_plugins(_str(node)):
        return 'plugins-join'
    if isinstance(node, ast.Call) and node.args and _ends_in_plugins(_str(node.args[-1])):
        return 'plugins-join'                      # Path("plugins") / "x", Path(root, "plugins") / "x"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and _ends_in_plugins(_str(node.right)):
        return 'plugins-join'                      # root / "plugins" / "x"
    ident = _ident(node)
    if ident and _PLUGINS_DIR_NAME_RE.search(ident):
        return 'plugins-dir-join'                  # PLUGINS_DIR / "x"
    return None


def _is_services(node) -> bool:
    if isinstance(node, ast.Call):
        return _ident(node.func) == 'get_services'
    return _ident(node) == 'services'


def _py_findings(text: str, rel: str, other) -> list[Finding]:
    """Takes Python source, produces its findings. Raises SyntaxError/ValueError if it does not parse."""
    tree = ast.parse(text)
    lines = text.splitlines()
    # bare string statements (docstrings) are prose, not code
    prose = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and _str(n.value) is not None}
    findings: list[Finding] = []

    def add(category, subtype, node, token):
        lineno = getattr(node, 'lineno', 0)
        raw = lines[lineno - 1] if 0 < lineno <= len(lines) else ''
        if _SUPPRESS_MARKER not in raw:
            findings.append(Finding(category, subtype, rel, lineno, token, raw.strip(), _HINTS[category]))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split('.')
                if parts[0] == 'plugins' and len(parts) > 1 and other(parts[1]):
                    add('import-other-plugin', 'import', node, f'plugins.{parts[1]}')
        elif isinstance(node, ast.ImportFrom):
            parts = (node.module or '').split('.')
            if node.level == 0 and parts[0] == 'plugins':
                names = parts[1:2] or [alias.name for alias in node.names]
                for name in names:
                    if other(name):
                        add('import-other-plugin', 'import', node, f'plugins.{name}')
        elif _str(node) is not None and id(node) not in prose:
            for m in _MODULE_STRING_RE.finditer(node.value):
                if other(m.group(1)):
                    add('import-other-plugin', 'module-string', node, f'plugins.{m.group(1)}')
            for m in _PATH_LITERAL_RE.finditer(node.value):
                if other(m.group(1)):
                    add('path-read-other-plugin', 'path-literal', node, m.group(1))
            for m in _REST_MOUNT_RE.finditer(node.value):
                if other(m.group(1)):
                    add('rest-mount-other-plugin', 'rest-mount', node, m.group(1))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and _str(node.right):
            name = _first_segment(node.right.value)
            subtype = _plugins_dir_spelling(node.left)
            if subtype and other(name):
                add('path-read-other-plugin', subtype, node, name)
            ident = _ident(node.left)
            if ident and _DIR_NAME_RE.search(ident) and other(name, needs_discovery=True):
                add('path-read-other-plugin', 'dir-join', node, name)
        elif isinstance(node, ast.Call):
            for a, b in zip(node.args, node.args[1:]):   # os.path.join(..., "plugins", "x")
                if _ends_in_plugins(_str(a)) and _str(b) and other(_first_segment(b.value)):
                    add('path-read-other-plugin', 'plugins-join', node, _first_segment(b.value))
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == 'get' and _is_services(func.value)
                    and node.args and _str(node.args[0])):
                key = node.args[0].value
                if key not in _CORE_SERVICES and (key.endswith('_svc') or other(key, needs_discovery=True)):
                    add('noncore-service-lookup', 'service-get', node, key)
    return sorted(findings, key=lambda f: f.lineno)


def _js_code_lines(text: str):
    """Takes .vue/.js/.ts/.html source, produces (lineno, raw line, code part) for each line worth scanning.

    Skips ``//`` lines and ``/* */`` / ``<!-- -->`` blocks that OPEN a line.
    Only a marker at the start of a line counts, so one inside a string such as
    ``accept="image/*"`` does not start a comment; prose after code on the same
    line is scanned (it can add a finding, not hide one).
    """
    closer = None
    for i, raw in enumerate(text.splitlines(), start=1):
        code = raw
        if closer:
            pos = code.find(closer)
            if pos < 0:
                continue
            code, closer = code[pos + len(closer):], None
        while True:
            stripped = code.lstrip()
            if stripped.startswith('//'):
                code = ''
                break
            opener = next((o for o in ('/*', '<!--') if stripped.startswith(o)), None)
            if opener is None:
                break
            end = '*/' if opener == '/*' else '-->'
            rest = stripped[len(opener):]
            pos = rest.find(end)
            if pos < 0:
                code, closer = '', end
                break
            code = rest[pos + len(end):]
        if _SUPPRESS_MARKER in raw or not code.strip():
            continue
        yield i, raw, code


def scan_text(text: str, others: set[str], rel: str = '<text>', hub: str = _HUB_NAME) -> list[Finding]:
    """Pure scanning core (no file IO), the guard tests exercise this directly.

    Takes source text, the discovered other plugins, its relpath (the suffix picks
    Python or .vue/.js/... rules) and the hub's own name; produces findings.
    Raises SyntaxError/ValueError for Python that does not parse.
    """
    def other(name: str, needs_discovery: bool = False) -> bool:
        if name == hub:
            return False
        return name in others if needs_discovery else True

    if not rel.endswith(_JS_SUFFIXES):
        return _py_findings(text, rel, other)
    findings: list[Finding] = []
    for i, raw, code in _js_code_lines(text):
        for m in _PATH_LITERAL_RE.finditer(code):
            if other(m.group(1)):
                findings.append(Finding('path-read-other-plugin', 'path-literal', rel, i,
                                        m.group(1), raw.strip(),
                                        _HINTS['path-read-other-plugin']))
        for m in _REST_MOUNT_RE.finditer(code):
            if other(m.group(1)):
                findings.append(Finding('rest-mount-other-plugin', 'rest-mount', rel, i,
                                        m.group(1), raw.strip(),
                                        _HINTS['rest-mount-other-plugin']))
    return findings


def scan_file(path: Path, others: set[str], rel: Path) -> list[Finding]:
    """Takes a file and its relpath, produces its findings. Raises OSError/ValueError/SyntaxError if unreadable."""
    return scan_text(path.read_text(encoding='utf-8'), others, rel.as_posix())


def _load_baseline(hub_root: Path) -> set[str]:
    bp = hub_root / 'tools' / _BASELINE_NAME
    if not bp.exists():
        return set()
    return {ln.strip() for ln in bp.read_text(encoding='utf-8').splitlines()
            if ln.strip() and not ln.startswith('#')}


def _write_baseline(hub_root: Path, keys: list[str]) -> Path:
    bp = hub_root / 'tools' / _BASELINE_NAME
    header = (
        '# hub_agnostic_baseline.txt — KNOWN hub->other-plugin couplings (GATING\n'
        '# categories only) accepted as debt to burn down. check_hub_agnostic.py\n'
        '# --strict fails on any GATING finding NOT listed here, so no NEW coupling\n'
        '# can land. Regenerate with: python tools/check_hub_agnostic.py --update-baseline\n'
        '# Each fix should SHRINK this file. One key per line: category|relpath|subtype|token\n'
    )
    bp.write_text(header + '\n'.join(sorted(set(keys))) + '\n', encoding='utf-8')
    return bp


def _collect(targets, others, hub_root) -> tuple[list[Finding], int, list[str]]:
    """Takes scan targets, produces (findings, files scanned, unreadable or unparseable 'path: reason' entries)."""
    files, missing = _iter_files(targets, hub_root)
    unreadable = [f'{m}: does not exist' for m in missing]
    findings, seen, scanned = [], set(), 0
    for f, rel in files:
        try:
            found = scan_file(f, others, rel)
        except (OSError, ValueError, SyntaxError) as e:   # UnicodeDecodeError is a ValueError
            unreadable.append(f'{rel.as_posix()}: {type(e).__name__}: {e}')
            continue
        scanned += 1
        for fd in found:
            dedup = (fd.category, fd.relpath, fd.lineno, fd.token)
            if dedup in seen:
                continue
            seen.add(dedup)
            findings.append(fd)
    return findings, scanned, unreadable


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Report MCP-hub couplings to specific other plugins.')
    ap.add_argument('paths', nargs='*')
    ap.add_argument('--strict', action='store_true',
                    help='exit 1 on a NEW (non-baselined) gating finding, an unreadable file, or no file scanned')
    ap.add_argument('--quiet', action='store_true')
    ap.add_argument('--update-baseline', action='store_true', help='rewrite the baseline from current gating findings')
    args = ap.parse_args(argv)

    hub_root = _hub_root()
    others = discover_other_plugins()
    targets = ([Path(p) for p in args.paths] if args.paths else _default_scan_targets())
    findings, scanned, unreadable = _collect(targets, others, hub_root)
    gating = [f for f in findings if f.category in _GATING]

    if args.update_baseline:
        bp = _write_baseline(hub_root, [f.key() for f in gating])
        print(f'[hub-agnostic] wrote {len({f.key() for f in gating})} gating keys to {bp}')
        return 0

    baseline = _load_baseline(hub_root)
    new_gating = [f for f in gating if f.key() not in baseline]

    print(f'[hub-agnostic] other plugins discovered: {len(others)}; '
          f'files scanned: {scanned} ({", ".join(_SOURCE_SUFFIXES)})')
    if not others:
        print(f'[hub-agnostic] NOTE: no sibling plugin found beside this one (a standalone checkout?). '
              f'Imports, plugins.<x> / plugins/<x> / /plugin/<x> strings and joins onto "plugins" are '
              f'still checked for every name except {_HUB_NAME!r}; '
              f'the generic <x>_dir|_root|_path|parent / "<name>" join is NOT checked here.')
    for u in unreadable:
        print(f'[hub-agnostic] UNREADABLE, not scanned: {u}')
    if not args.quiet:
        by_cat: dict[str, list[Finding]] = {}
        for f in findings:
            by_cat.setdefault(f.category, []).append(f)
        for cat in _CATEGORY_ORDER:
            items = by_cat.get(cat) or []
            if not items:
                continue
            tag = 'GATE' if cat in _GATING else 'warn'
            print(f'\n== {cat} [{tag}] ({len(items)}) ==\n   hint: {_HINTS[cat]}')
            for f in items:
                mark = (' [NEW]' if f.key() not in baseline else ' [baselined]') if cat in _GATING else ''
                print(f'   {f.relpath}:{f.lineno}: {f.token} ({f.subtype}){mark}  | {f.line[:80]}')

    counts = Counter(f.category for f in findings)
    print('\n[hub-agnostic] summary: ' + ', '.join(f'{c}={counts.get(c, 0)}' for c in _CATEGORY_ORDER))
    print(f'[hub-agnostic] gating: {len(gating)} total, '
          f'{len(gating) - len(new_gating)} baselined (known debt), {len(new_gating)} NEW')

    if args.strict and new_gating:
        print('\n[hub-agnostic] FAIL: new hub->plugin coupling(s) not in the baseline:')
        for f in new_gating:
            print(f'   {f.relpath}:{f.lineno}: {f.key()}')
        print('Fix: reach the plugin via its interface (service by capability / MCP tool '
              '/ REST). If truly intentional, add `# hub-agnostic-ok: <reason>` on the line.')
        return 1
    if args.strict and (unreadable or not scanned):
        print(f'\n[hub-agnostic] FAIL: {len(unreadable)} unreadable path(s), {scanned} file(s) scanned; '
              'the gate cannot vouch for what it did not read.')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
