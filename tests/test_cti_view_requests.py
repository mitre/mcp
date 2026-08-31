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

CTI_VUE = Path(__file__).resolve().parents[1] / "gui" / "views" / "cti.vue"

SOURCE = CTI_VUE.read_text(encoding="utf-8")
SCRIPT = re.search(r"<script setup>(.*?)</script>", SOURCE, re.S).group(1)
TEMPLATE = re.search(r"<template>(.*?)\n</template>", SOURCE, re.S).group(1)


class TestEveryRequestIsChecked:
    def test_the_view_still_talks_to_the_server(self):
        """Guards the two tests below from passing on an empty read."""
        assert SCRIPT.strip(), "no <script setup> block found"
        assert "requestJson(" in SCRIPT

    def test_only_the_helper_calls_fetch(self):
        """A bare fetch is a call site that forgot the session check."""
        calls = [
            line.strip()
            for line in SCRIPT.splitlines()
            if re.search(r"\bfetch\(", line)
        ]
        assert calls == ["res = await fetch(url, options)"], (
            f"fetch called outside request(): {calls}"
        )

    def test_the_helper_looks_past_the_status_code(self):
        """res.ok alone is true for the login page, so the redirect and the
        explicit refusals both have to be inspected."""
        assert "res.redirected" in SCRIPT
        assert "res.status === 401" in SCRIPT
        assert "res.status === 403" in SCRIPT
        assert "if (!res.ok)" in SCRIPT


class TestTheStatusBannerCanBeDismissed:
    def test_the_banner_is_present(self):
        """Guards the two tests below from passing on a missing banner."""
        assert 'class="notification mt-4"' in TEMPLATE

    def test_the_banner_has_a_close_control(self):
        """Matches the delete button stixViewer.vue already uses."""
        banner = TEMPLATE[TEMPLATE.index('class="notification mt-4"'):]
        assert 'class="delete"' in banner[:400]

    def test_the_banner_tone_is_not_hardcoded(self):
        """A failed upload rendered in the same blue box as a success."""
        assert "notification is-info" not in TEMPLATE
        assert ":class=\"`is-${ctiStatus.tone}`\"" in TEMPLATE
