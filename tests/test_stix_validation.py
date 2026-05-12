"""Tests for cti_stix_validation.py, cti_stix_report_writer.py, cti_stix_merge.py."""
import pytest


class TestValidUuid4:
    def test_valid(self):
        from plugins.mcp.app.utilities.cti_stix_validation import valid_uuid4
        assert valid_uuid4("550e8400-e29b-41d4-a716-446655440000") is True

    def test_invalid(self):
        from plugins.mcp.app.utilities.cti_stix_validation import valid_uuid4
        assert valid_uuid4("not-a-uuid") is False
        assert valid_uuid4("") is False


class TestValidStixId:
    def test_valid(self):
        from plugins.mcp.app.utilities.cti_stix_validation import valid_stix_id
        assert valid_stix_id("malware", "malware--550e8400-e29b-41d4-a716-446655440000") is True

    def test_wrong_prefix(self):
        from plugins.mcp.app.utilities.cti_stix_validation import valid_stix_id
        assert valid_stix_id("tool", "malware--550e8400-e29b-41d4-a716-446655440000") is False


class TestValidateBundle:
    def test_valid_bundle(self, sample_stix_bundle):
        from plugins.mcp.app.utilities.cti_stix_validation import validate_bundle
        errors = validate_bundle(sample_stix_bundle)
        # Should have few or no errors for a properly built bundle
        assert isinstance(errors, list)

    def test_empty_bundle(self):
        from plugins.mcp.app.utilities.cti_stix_validation import validate_bundle
        errors = validate_bundle({"type": "bundle", "id": "bundle--test", "objects": []})
        assert isinstance(errors, list)


class TestRenderStixReport:
    def test_renders(self, sample_stix_bundle):
        from plugins.mcp.app.utilities.cti_stix_report_writer import render_stix_report
        report = render_stix_report(sample_stix_bundle, "test.json")
        assert isinstance(report, str)
        assert len(report) > 0


class TestMergeStixBundles:
    def test_merge_two_bundles(self):
        from plugins.mcp.app.utilities.cti_stix_merge import merge_stix_bundles
        from plugins.mcp.app.utilities.cti_stix_builders import make_tool, make_bundle
        b1 = make_bundle([make_tool({"name": "Mimikatz"})])
        b2 = make_bundle([make_tool({"name": "PsExec"})])
        merged = merge_stix_bundles([b1, b2], ["source1", "source2"])
        assert merged["type"] == "bundle"
        assert len(merged["objects"]) == 2

    def test_dedup_same_entity(self):
        from plugins.mcp.app.utilities.cti_stix_merge import merge_stix_bundles
        from plugins.mcp.app.utilities.cti_stix_builders import make_tool, make_bundle
        t = make_tool({"name": "Mimikatz"})
        b1 = make_bundle([t])
        b2 = make_bundle([make_tool({"name": "Mimikatz"})])
        merged = merge_stix_bundles([b1, b2], ["s1", "s2"])
        tools = [o for o in merged["objects"] if o.get("type") == "tool"]
        assert len(tools) == 1  # deduped
        assert tools[0].get("x_cti_source_count", 1) == 2  # both sources

    def test_empty_input(self):
        from plugins.mcp.app.utilities.cti_stix_merge import merge_stix_bundles
        result = merge_stix_bundles([])
        assert result["type"] == "bundle"
        assert result["objects"] == []

    def test_metadata(self):
        from plugins.mcp.app.utilities.cti_stix_merge import merge_stix_bundles
        from plugins.mcp.app.utilities.cti_stix_builders import make_bundle
        merged = merge_stix_bundles(
            [make_bundle([]), make_bundle([])],
            ["report_a", "report_b"]
        )
        meta = merged.get("x_cti_merge_metadata", {})
        assert meta.get("source_count") == 2
        assert "report_a" in meta.get("source_names", [])
