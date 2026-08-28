"""Tests for cti_pipeline_stage2.py — IR to STIX conversion."""
import json


class TestLoadIr:
    def test_loads_valid(self, tmp_path):
        from plugins.mcp.app.cti_pipeline_stage2 import load_ir
        ir = {"threat_actors": [], "malware": [], "tools": [], "attack_patterns": []}
        f = tmp_path / "test.json"
        f.write_text(json.dumps(ir))
        result = load_ir(f)
        assert result == ir

    def test_missing_file(self, tmp_path):
        from plugins.mcp.app.cti_pipeline_stage2 import load_ir
        result = load_ir(tmp_path / "nonexistent.json")
        assert result == {}

    def test_invalid_json(self, tmp_path):
        from plugins.mcp.app.cti_pipeline_stage2 import load_ir
        f = tmp_path / "bad.json"
        f.write_text("not json")
        result = load_ir(f)
        assert result == {}


class TestComputeMetrics:
    def test_counts(self):
        from plugins.mcp.app.cti_pipeline_stage2 import compute_metrics
        ir = {"threat_actors": [1], "attack_patterns": [1, 2, 3],
              "behaviors": [1], "hashes": [1, 2]}
        bundle = {"objects": [
            {"type": "attack-pattern"}, {"type": "threat-actor"},
            {"type": "observed-data"},
        ]}
        metrics = compute_metrics(ir, bundle)
        assert metrics["input_counts"]["attack_patterns"] == 3
        assert metrics["input_counts"]["hashes"] == 2
        assert metrics["output_counts"]["total_stix_objects"] == 3
        assert metrics["output_counts"]["attack_patterns"] == 1
        assert metrics["output_counts"]["threat_actors"] == 1

    def test_counts_only_producible_types(self):
        """Counting types the pipeline can no longer emit made the metrics
        file a wall of zeros that read like extraction had failed."""
        from plugins.mcp.app.cti_pipeline_stage2 import compute_metrics
        metrics = compute_metrics({}, {"objects": []})
        dead = {"malware", "tools", "infrastructure", "relationships",
                "domains", "user_accounts", "software", "identities"}
        assert not (set(metrics["input_counts"]) & dead)
        assert not (set(metrics["output_counts"]) & dead)


class TestConvertIrToStix:
    def test_converts_basic_ir(self, taxonomy, sample_ir):
        from plugins.mcp.app.cti_pipeline_stage2 import convert_ir_to_stix
        sample_ir["provenance"] = {"provider": "test", "model": "test"}
        debug = {}
        bundle = convert_ir_to_stix(sample_ir, debug, taxonomy)
        assert bundle["type"] == "bundle"
        assert len(bundle["objects"]) >= 3  # actors + malware + tools

    def test_handles_empty_ir(self, taxonomy):
        from plugins.mcp.app.cti_pipeline_stage2 import convert_ir_to_stix
        ir = {"threat_actors": [], "malware": [], "tools": [],
              "infrastructure": [], "attack_patterns": [], "behaviors": [],
              "relationships": [], "provenance": {"provider": "test", "model": "test"}}
        debug = {}
        bundle = convert_ir_to_stix(ir, debug, taxonomy)
        assert bundle["type"] == "bundle"


class TestWriteDebugFile:
    def test_writes_json(self, tmp_path):
        from plugins.mcp.app.cti_pipeline_stage2 import write_debug_file
        f = tmp_path / "debug" / "test.json"
        write_debug_file(f, {"key": "value"})
        assert f.exists()
        assert json.loads(f.read_text()) == {"key": "value"}

    def test_writes_text(self, tmp_path):
        from plugins.mcp.app.cti_pipeline_stage2 import write_debug_file
        f = tmp_path / "debug" / "test.txt"
        write_debug_file(f, "hello world")
        assert f.exists()
        assert f.read_text() == "hello world"

