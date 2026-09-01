"""The CTI view must route every request through its checked helper.

Caldera gates plugin routes per handler, and check_permissions answers an
expired session by raising HTTPFound('/login'). fetch follows that redirect,
so the reply reaches the browser as a 200 carrying the login page. Checking
res.ok is not enough to catch it, and a bare fetch caught nothing at all: the
tables just rendered empty. These are static guards, because the plugin ships
no JavaScript test runner.
"""
import re
from pathlib import Path

GUI = Path(__file__).resolve().parents[1] / "gui"
CTI_VUE = GUI / "views" / "cti.vue"
MODEL_PANEL = GUI / "components" / "modelSelector.vue"
REQUEST_JS = GUI / "composables" / "request.js"

SOURCE = CTI_VUE.read_text(encoding="utf-8")
HELPER = REQUEST_JS.read_text(encoding="utf-8") if REQUEST_JS.exists() else ""
PANEL = MODEL_PANEL.read_text(encoding="utf-8") if MODEL_PANEL.exists() else ""


def _block(pattern):
    """Return a block of cti.vue, or "" if the tag is no longer recognisable.

    Deliberately not an assert: raising here happens at import, and pytest
    treats a collection error as fatal to the whole run, so renaming a tag in
    a .vue file would silence every other suite. The empty string fails the
    guards below instead, where the message says what went wrong.
    """
    match = re.search(pattern, SOURCE, re.S)
    return match.group(1) if match else ""


SCRIPT = _block(r"<script setup>(.*?)\n</script>")
TEMPLATE = _block(r"<template>(.*?)\n</template>")


class TestEveryRequestIsChecked:
    def test_the_view_still_talks_to_the_server(self):
        """Guards the two tests below from passing on an empty read."""
        assert SCRIPT.strip(), "cti.vue has no readable <script setup> block"
        assert "requestJson(" in SCRIPT

    def test_the_shared_helper_exists(self):
        """Both CTI-page files import it, so its absence must fail loudly."""
        assert HELPER.strip(), f"{REQUEST_JS} is missing or empty"
        assert PANEL.strip(), f"{MODEL_PANEL} is missing or empty"

    def test_no_cti_page_file_calls_fetch_directly(self):
        """A bare fetch is a call site that forgot the session check. The one
        real fetch belongs to the shared helper and nowhere else."""
        for name, src in (("cti.vue", SCRIPT), ("modelSelector.vue", PANEL)):
            calls = [ln.strip() for ln in src.splitlines() if re.search(r"\bfetch\(", ln)]
            assert not calls, f"{name} calls fetch outside the helper: {calls}"

        helper_calls = [ln.strip() for ln in HELPER.splitlines() if re.search(r"\bfetch\(", ln)]
        assert helper_calls == ["res = await fetch(url, options)"], (
            f"unexpected fetch in the helper: {helper_calls}"
        )

    def test_both_files_route_through_the_helper(self):
        """Importing it is what makes the guard above meaningful."""
        assert "composables/request.js" in SCRIPT, "cti.vue does not import the helper"
        assert "composables/request.js" in PANEL, "modelSelector.vue does not import the helper"

    def test_the_helper_looks_past_the_status_code(self):
        """res.ok alone is true for the login page, so the redirect and the
        explicit refusals both have to be inspected."""
        assert "res.redirected" in HELPER
        assert "res.status === 401" in HELPER
        assert "res.status === 403" in HELPER
        assert "if (!res.ok)" in HELPER

    def test_the_panel_cannot_report_a_save_that_did_not_happen(self):
        """An expired session answers 200 with the login page, so the old
        `if (!res.ok)` let the panel show a green Saved for nothing."""
        assert "await request(" in PANEL, "the panel does not use the checked helper"
        assert "if (!res.ok)" not in PANEL, "the panel still trusts res.ok"


class TestTheStatusBannerCanBeDismissed:
    def test_the_banner_is_present(self):
        """Guards the two tests below from passing on a missing banner."""
        assert TEMPLATE.strip(), "cti.vue has no readable <template> block"
        assert 'class="notification mt-4"' in TEMPLATE

    def test_the_banner_has_a_close_control(self):
        """Matches the delete button stixViewer.vue already uses."""
        start = TEMPLATE.find('class="notification mt-4"')
        assert start >= 0, "the status banner is gone"
        assert 'class="delete"' in TEMPLATE[start:start + 400]

    def test_the_banner_tone_is_not_hardcoded(self):
        """A failed upload rendered in the same blue box as a success."""
        assert "notification is-info" not in TEMPLATE
        assert ":class=\"`is-${ctiStatus.tone}`\"" in TEMPLATE
