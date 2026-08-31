"""Each DSPy step returns a Prediction, and the next step declares list[str].

Passing the whole Prediction made DSPy stringify it, reasoning included, into
the next prompt: the ranker received a paragraph of prose where its signature
declared a list, and warned on every call.
"""
import sys
import types

import pytest


class _Prediction:
    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __repr__(self):
        return f"Prediction({self.__dict__})"


@pytest.fixture
def chain(monkeypatch):
    from plugins.mcp.app import dspy_env

    seen = {}

    def _stub(signature):
        name = signature.__name__

        def _call(**kwargs):
            seen[name] = kwargs
            if name == "IdentifyTechnologies":
                return _Prediction(reasoning="because powershell", technologies=["PowerShell"])
            if name == "RankApproaches":
                return _Prediction(reasoning="ranked", approaches=["run in powershell"])
            return _Prediction(reasoning="built", command="powershell.exe -Command echo hi")

        return _call

    monkeypatch.setattr(dspy_env, "ensure_lm_configured", lambda: None)
    monkeypatch.setattr(dspy_env.dspy, "ChainOfThought", _stub)
    return dspy_env.CreateCommand(), seen


def test_each_step_receives_the_field_not_the_prediction(chain):
    module, seen = chain
    module.forward(description="echo hi", platform="windows")

    assert seen["RankApproaches"]["technologies"] == ["PowerShell"]
    assert seen["CreateFullCommand"]["technologies"] == ["PowerShell"]
    assert seen["CreateFullCommand"]["approaches"] == ["run in powershell"]

    for step, field in (("RankApproaches", "technologies"),
                        ("CreateFullCommand", "technologies"),
                        ("CreateFullCommand", "approaches")):
        assert not isinstance(seen[step][field], _Prediction), (
            f"{step}.{field} got a Prediction, which DSPy stringifies into the prompt"
        )


def test_it_still_returns_the_command_string(chain):
    module, _ = chain
    assert module.forward(description="echo hi", platform="windows") == (
        "powershell.exe -Command echo hi"
    )
