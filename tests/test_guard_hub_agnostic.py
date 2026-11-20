"""Guard-rail tests for the hub plugin-agnosticism gate (tools/check_hub_agnostic.py).

The MCP hub must reference NO specific other plugin, it discovers and drives
plugins generically. These tests pin the scanner's behaviour (so a future edit
that blinds a category or trips on benign code FAILS here) AND enforce the live
contract: ``--strict`` must stay green against the burn-down baseline, so no NEW
hub->plugin coupling can land. The baseline (tools/hub_agnostic_baseline.txt)
should only ever SHRINK.

Inline fixtures on the pure ``scan_text`` core, plus throwaway plugin trees
under tmp_path for the end-to-end runs. No network.
"""
import importlib.util
import os

import pytest

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TOOL_PATH = os.path.join(_PLUGIN_ROOT, 'tools', 'check_hub_agnostic.py')


def _load():
    spec = importlib.util.spec_from_file_location('check_hub_agnostic', _TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hga = _load()
# A fixed "other plugins" set so the fixtures don't depend on what's installed.
_OTHERS = {'pluginx', 'pluginy', 'pluginz'}


def _cats(text):
    return {f.category for f in hga.scan_text(text, _OTHERS)}


def _subtypes(text):
    return {f.subtype for f in hga.scan_text(text, _OTHERS)}


# --- import-other-plugin (GATE) -------------------------------------------
def test_import_other_plugin_trips():
    assert 'import-other-plugin' in _cats('from plugins.pluginx.app.some_svc import X')
    assert 'import-other-plugin' in _cats('import plugins.pluginy.foo')


def test_import_self_or_core_does_not_trip():
    assert 'import-other-plugin' not in _cats('from plugins.mcp.app.config import Y')
    assert 'import-other-plugin' not in _cats('from app.utility.base_world import BaseWorld')


# --- path-read-other-plugin (GATE) ----------------------------------------
def test_path_read_forms_trip():
    assert 'path-literal' in _subtypes('p = Path("plugins/pluginx/conf/images.yml")')
    assert 'plugins-join' in _subtypes('_PLUGINX_DIR = _REPO_ROOT / "plugins" / "pluginx"')
    assert 'dir-join' in _subtypes('x_conf = mcp_root.parent / "pluginx" / "conf"')
    assert 'dir-join' in _subtypes('p = (plugins_dir / "pluginy" / "data").glob("x")')


def test_path_read_in_docstring_is_ignored():
    # prose in a docstring that mentions a plugin path is NOT a read
    doc = '"""\nLoads plugins/pluginx/conf/images.yml at boot.\n"""'
    assert 'path-read-other-plugin' not in _cats(doc)


# --- rest-mount-other-plugin (GATE) ---------------------------------------
def test_rest_mount_trips_other_but_not_self():
    assert 'rest-mount-other-plugin' in _cats('r = request.get("/plugin/pluginx/api/images")')
    assert 'rest-mount-other-plugin' not in _cats('r = request.get("/plugin/mcp/servers")')


# --- standalone checkout: forms that name the plugin need no discovery ----
def test_pattern_forms_trip_without_discovered_plugins():
    text = ('from plugins.pluginx.app import x\n'
            'p = Path("plugins/pluginx/data/a.yml")\n'
            'q = REPO / "plugins" / "pluginx"\n'
            'r = plugins_root / "pluginx"\n'
            'u = "/plugin/pluginx/api"\n')
    assert {(f.lineno, f.category, f.subtype) for f in hga.scan_text(text, set())} == {
        (1, 'import-other-plugin', 'import'),
        (2, 'path-read-other-plugin', 'path-literal'),
        (3, 'path-read-other-plugin', 'plugins-join'),
        (4, 'path-read-other-plugin', 'plugins-dir-join'),
        (5, 'rest-mount-other-plugin', 'rest-mount'),
    }
    # the hub's own name never trips, discovered or not
    assert hga.scan_text('from plugins.mcp.app import y\nu = "/plugin/mcp/api"\n'
                         'r = plugins_root / "mcp"\n', set()) == []


def test_generic_dir_join_needs_the_discovered_set():
    assert hga.scan_text('x = base_dir / "conf"', set()) == []
    assert {f.subtype for f in hga.scan_text('x = base_dir / "pluginx"', _OTHERS)} == {'dir-join'}


# --- more spellings of the same couplings (Python parsed with ast) ---------
@pytest.mark.parametrize('rel, text, expected', [
    pytest.param('<text>', 'from plugins import pluginx\n',
                 ('import-other-plugin', 'import', 'plugins.pluginx'), id='from-plugins-import-name'),
    pytest.param('<text>', 'import importlib\nm = importlib.import_module("plugins.pluginx.app.x")\n',
                 ('import-other-plugin', 'module-string', 'plugins.pluginx'), id='import-module-string'),
    pytest.param('<text>', 'c = "#"; from plugins.pluginx.app import x\n',
                 ('import-other-plugin', 'import', 'plugins.pluginx'), id='hash-in-string-earlier-on-the-line'),
    pytest.param('<text>', 'import os\np = os.path.join("plugins", "pluginx", "data")\n',
                 ('path-read-other-plugin', 'plugins-join', 'pluginx'), id='os-path-join'),
    pytest.param('<text>', 'p = Path("plugins") / "pluginx"\n',
                 ('path-read-other-plugin', 'plugins-join', 'pluginx'), id='path-call-join'),
    pytest.param('<text>', 'p = Path("plugins/pluginx")\n',
                 ('path-read-other-plugin', 'path-literal', 'pluginx'), id='literal-without-trailing-slash'),
    pytest.param('<text>', 'p = PLUGINS_DIR / "pluginx"\n',
                 ('path-read-other-plugin', 'plugins-dir-join', 'pluginx'), id='upper-case-plugins-dir'),
    pytest.param('<text>', 'p = open("plugins/plugin-x/data/x.yml")\n',
                 ('path-read-other-plugin', 'path-literal', 'plugin-x'), id='hyphenated-literal'),
    pytest.param('<text>', 'u = "/plugin/plugin-x/api"\n',
                 ('rest-mount-other-plugin', 'rest-mount', 'plugin-x'), id='hyphenated-mount'),
    pytest.param('<text>', 'u = "/plugin/pluginx"\n',
                 ('rest-mount-other-plugin', 'rest-mount', 'pluginx'), id='mount-without-trailing-slash'),
    pytest.param('gui/views/x.vue', "fetch('/plugin/pluginx')\n",
                 ('rest-mount-other-plugin', 'rest-mount', 'pluginx'), id='js-mount-without-trailing-slash'),
    pytest.param('gui/views/x.vue', "fetch('/plugin/plugin-x/api')\n",
                 ('rest-mount-other-plugin', 'rest-mount', 'plugin-x'), id='js-hyphenated-mount'),
])
def test_more_spellings_trip_without_discovered_plugins(rel, text, expected):
    assert {(f.category, f.subtype, f.token) for f in hga.scan_text(text, set(), rel)} == {expected}


def test_benign_code_and_documented_limits_do_not_trip():
    py = ('log = logging.getLogger("plugins.mcp")\n'      # the hub itself
          '# from plugins.pluginx.app import x\n'          # a comment
          'def f():\n    """Reads plugins/pluginx/conf at boot."""\n'
          'p = plugin_dir / "conf"\n'                      # per-plugin discovery, not a name
          'q = base_dir / "pluginx"\n'                     # LIMIT: arbitrary variable join
          'r = Path(__file__).parent.parent / "pluginx"\n'  # LIMIT: same
          'u = "/plugin/" + name + "/api"\n'               # LIMIT: computed name
          'v = f"plugins/{name}/data"\n'                   # LIMIT: computed name
          'from ..pluginx import y\n')                     # LIMIT: relative import
    assert hga.scan_text(py, set()) == []
    js = ('plugins.map(p => p.name)\n'                     # ordinary JS code
          "fetch('/plugin/' + 'pluginx' + '/api')\n"       # LIMIT: concatenated
          "import X from '../../../pluginx/gui/x.vue'\n")  # LIMIT: relative path
    assert hga.scan_text(js, set(), 'gui/views/x.vue') == []


# --- gui sources (.vue / .js) ----------------------------------------------
def test_vue_and_js_comments_are_skipped_but_code_is_not():
    vue = ('<!--\n  talks to /plugin/pluginx/api, in prose only\n-->\n'
           '// fetch("/plugin/pluginx/old")\n'
           '/* plugins/pluginx/ in a comment */\n'
           "const c = '#222'; fetch('/plugin/pluginx/api')\n")
    found = hga.scan_text(vue, set(), 'gui/views/x.vue')
    assert [(f.lineno, f.category) for f in found] == [(6, 'rest-mount-other-plugin')]


# --- end to end on a throwaway checkout with no sibling plugins -------------
def _hub(tmp_path, *parents):
    root = tmp_path.joinpath(*parents, 'mcp')
    (root / 'app').mkdir(parents=True)
    (root / 'gui').mkdir()
    (root / 'app' / 'ok.py').write_text('from plugins.mcp.app.config import y\n')
    return root


def _strict(monkeypatch, root):
    monkeypatch.setattr(hga, '_hub_root', lambda: root)
    return hga.main(['--strict', '--quiet'])


@pytest.mark.parametrize('parents', [(), ('build', 'tools')])
def test_standalone_checkout_gates_python_and_gui(tmp_path, monkeypatch, capsys, parents):
    # parents: a checkout that itself lives under directories named like excluded ones
    root = _hub(tmp_path, *parents)
    (root / 'gui' / 'x.vue').write_text("<script>fetch('/plugin/pluginx/api')</script>\n")
    assert _strict(monkeypatch, root) == 1
    (root / 'gui' / 'x.vue').unlink()
    (root / 'app' / 'bad.py').write_text('from plugins.pluginx.app import x\n')
    assert _strict(monkeypatch, root) == 1
    (root / 'app' / 'bad.py').unlink()
    capsys.readouterr()
    assert _strict(monkeypatch, root) == 0
    out = capsys.readouterr().out
    assert 'other plugins discovered: 0; files scanned: 1' in out
    assert 'NOT checked here' in out


@pytest.mark.parametrize('rel', [
    'app/tools/x.py', 'app/tests/x.py', 'app/vendor/x.py', 'gui/build/x.js',
    'gui/x.mjs', 'gui/x.ts', 'gui/x.tsx', 'templates/x.html', 'static/js/x.js',
])
def test_every_source_dir_and_type_is_scanned(tmp_path, monkeypatch, rel):
    root = _hub(tmp_path)
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text('from plugins.pluginx.app import x\n' if rel.endswith('.py')
                 else "fetch('/plugin/pluginx/api')\n")
    assert _strict(monkeypatch, root) == 1


def test_clean_hub_across_every_scanned_dir_passes(tmp_path, monkeypatch, capsys):
    root = _hub(tmp_path)
    for rel, text in (('templates/mcp.html', "<a href='/plugin/mcp/gui'>mcp</a>\n"),
                      ('static/js/mcp.js', "fetch('/plugin/mcp/api')\n"),
                      ('gui/x.ts', "const own = '/plugin/mcp/servers'\n"),
                      ('gui/node_modules/dep/index.js', "fetch('/plugin/pluginx/api')\n")):  # third-party
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    assert _strict(monkeypatch, root) == 0
    assert 'files scanned: 4' in capsys.readouterr().out


def test_unparseable_python_fails_strict(tmp_path, monkeypatch, capsys):
    root = _hub(tmp_path)
    (root / 'app' / 'broken.py').write_text('def f(:\n')
    assert _strict(monkeypatch, root) == 1
    assert 'UNREADABLE, not scanned: app/broken.py: SyntaxError' in capsys.readouterr().out


def test_unreadable_file_is_reported_and_fails_strict(tmp_path, monkeypatch, capsys):
    root = _hub(tmp_path)
    (root / 'app' / 'latin1.py').write_bytes(b'# caf\xe9\n')
    assert _strict(monkeypatch, root) == 1
    assert 'UNREADABLE, not scanned: app/latin1.py' in capsys.readouterr().out


# --- noncore-service-lookup (advisory) ------------------------------------
def test_noncore_service_lookup_trips_only_for_services_receiver():
    assert 'noncore-service-lookup' in _cats('svc = self.services.get("pluginy_svc")')
    # a plain dict .get is NOT a service lookup
    assert 'noncore-service-lookup' not in _cats('x = turn.get("response")')
    # a core service is allowlisted
    assert 'noncore-service-lookup' not in _cats('d = services.get("data_svc")')


# --- suppression + agnosticism --------------------------------------------
def test_inline_suppression_silences_a_line():
    assert 'import-other-plugin' not in _cats(
        'import plugins.pluginx.app.some_svc  # hub-agnostic-ok: bootstrap shim')


def test_discovery_is_dynamic_and_excludes_self_and_backups(tmp_path, monkeypatch):
    # A throwaway plugins/ tree, so the test does not depend on what is installed.
    plugins = tmp_path / 'plugins'
    for name in ('mcp', 'pluginx', 'pluginx-backup', 'pluginy-snapshot'):
        (plugins / name).mkdir(parents=True)
        (plugins / name / 'hook.py').write_text('')
    (plugins / 'no-hook').mkdir()
    monkeypatch.setattr(hga, '_hub_root', lambda: plugins / 'mcp')
    others = hga.discover_other_plugins()
    assert 'mcp' not in others                      # never flags the hub itself
    assert 'pluginx' in others                      # discovers installed plugins at runtime
    assert 'no-hook' not in others                  # a plugin is a dir shipping hook.py
    assert not any('backup' in n or 'snapshot' in n for n in others)


# --- the live contract: no NEW coupling beyond the baseline ---------------
def test_strict_is_green_against_baseline():
    # Fails if the hub gained a coupling not in tools/hub_agnostic_baseline.txt.
    # Fix by reaching the plugin through its interface; the baseline may only SHRINK.
    assert hga.main(['--strict', '--quiet']) == 0
