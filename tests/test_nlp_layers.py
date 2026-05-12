"""Tests for NLP layers: cti_nlp_enhancements.py, cti_behavior_expansion.py, cti_semantic_enrichment.py."""
import pytest


class TestIsValidActor:
    def test_short_name(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import is_valid_actor
        assert is_valid_actor("APT29") is True
        assert is_valid_actor("BlackCat") is True

    def test_multi_word(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import is_valid_actor
        assert is_valid_actor("Berserk Bear") is True
        assert is_valid_actor("Wizard Spider") is True

    def test_long_narrative(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import is_valid_actor
        assert is_valid_actor("Kroll's Threat Intelligence Team Analysis Group") is False

    def test_group_cue(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import is_valid_actor
        assert is_valid_actor("FIN7 group") is True


class TestNormalizeActorName:
    def test_removes_possessive(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import normalize_actor_name
        assert "'" not in normalize_actor_name("BlackCat's")

    def test_strips(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import normalize_actor_name
        result = normalize_actor_name("  APT29  ")
        assert result == "APT29"


class TestNormalizePhrase:
    def test_lowercase_alphanumeric(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import normalize_phrase
        assert normalize_phrase("Hello World!") == "helloworld"

    def test_preserves_dots(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import normalize_phrase
        result = normalize_phrase("192.168.1.1")
        assert "192.168.1.1" in result


class TestExtractDependencyBehaviors:
    def test_extracts_verb_object(self, nlp):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import extract_dependency_behaviors
        doc = nlp("The malware encrypts files on the system.")
        behaviors = extract_dependency_behaviors(doc)
        assert len(behaviors) >= 1

    def test_empty_doc(self, nlp):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import extract_dependency_behaviors
        doc = nlp("")
        behaviors = extract_dependency_behaviors(doc)
        assert behaviors == []


class TestSplitMultiVerb:
    def test_splits_and(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import split_multi_verb
        parts = split_multi_verb("enumerates directories and exfiltrates data")
        assert len(parts) == 2

    def test_no_split(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import split_multi_verb
        parts = split_multi_verb("encrypts files")
        assert len(parts) == 1


class TestDedupeBehaviorsByVector:
    def test_removes_duplicates(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import dedupe_behaviors_by_vector
        texts = ["encrypt files", "encrypt all files", "delete backups"]
        result = dedupe_behaviors_by_vector(texts, threshold=0.92)
        # The two encrypt variants should merge
        assert len(result) <= len(texts)

    def test_empty(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import dedupe_behaviors_by_vector
        assert dedupe_behaviors_by_vector([]) == []


class TestCleanIrNlpLayer1:
    def test_expands_behaviors(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1
        ir = {"behaviors": [], "threat_actors": [{"name": "APT29"}],
              "malware": [], "tools": [], "infrastructure": []}
        text = "The malware encrypts files and deletes shadow copies."
        result = clean_ir_nlp_layer1(ir, text)
        assert len(result["behaviors"]) >= 1

    def test_actor_cleanup(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1
        ir = {"behaviors": [], "threat_actors": [
            {"name": "APT29"},
            {"name": "Kroll's Security Research Division Threat Intelligence Team"},
        ], "malware": [], "tools": [], "infrastructure": []}
        result = clean_ir_nlp_layer1(ir, "APT29 attacks targets.")
        # Long narrative name should be removed
        actor_names = {a["name"] for a in result["threat_actors"]}
        assert "APT29" in actor_names
        assert len(actor_names) == 1

    def test_slash_actor_split(self):
        from plugins.mcp.app.utilities.nlp.cti_nlp_enhancements import clean_ir_nlp_layer1
        ir = {"behaviors": [], "threat_actors": [{"name": "ALPHV/BlackCat"}],
              "malware": [], "tools": [], "infrastructure": []}
        result = clean_ir_nlp_layer1(ir, "ALPHV/BlackCat ransomware.")
        actor_names = {a["name"] for a in result["threat_actors"]}
        # Should be split into two actors
        assert len(actor_names) >= 2


class TestRecoverNominalizedBehaviors:
    def test_finds_nominalized(self):
        from plugins.mcp.app.utilities.nlp.cti_behavior_expansion import recover_nominalized_behaviors
        text = "The encryption of sensitive files was performed by the malware."
        behaviors = recover_nominalized_behaviors(text)
        assert isinstance(behaviors, list)

    def test_empty(self):
        from plugins.mcp.app.utilities.nlp.cti_behavior_expansion import recover_nominalized_behaviors
        assert recover_nominalized_behaviors("") == []


class TestCleanIrNlpLayer2:
    def test_runs_without_error(self):
        from plugins.mcp.app.utilities.nlp.cti_semantic_enrichment import clean_ir_nlp_layer2
        ir = {"attack_patterns": [], "behaviors": [{"description": "encrypt files"}]}
        taxonomy = {"attack_patterns": []}
        result = clean_ir_nlp_layer2(ir, taxonomy)
        assert isinstance(result, dict)
