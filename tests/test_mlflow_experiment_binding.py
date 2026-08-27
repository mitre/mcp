"""Run/experiment binding for mlflow.start_run(run_id=...).

mlflow refuses to resume a run when the process-wide active experiment
differs from the run's. Two workflows using different experiment names
therefore broke every execution after the first.
"""
import mlflow
import pytest

from plugins.mcp.app.workflows.author import WORKFLOWS as AUTHOR_WORKFLOWS
from plugins.mcp.app.workflows.plan_execute import WORKFLOWS as PLAN_WORKFLOWS


@pytest.fixture
def tracking(tmp_path):
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")
    yield
    if mlflow.active_run():
        mlflow.end_run()


def test_every_workflow_declares_an_experiment():
    for wf in list(AUTHOR_WORKFLOWS) + list(PLAN_WORKFLOWS):
        assert wf.mlflow_experiment, f"{wf.id} has no experiment"


def test_author_and_plan_execute_do_not_share_an_experiment():
    """They are deliberately separate; the bug was mcp_svc ignoring that."""
    author = AUTHOR_WORKFLOWS[0].mlflow_experiment
    plan = PLAN_WORKFLOWS[0].mlflow_experiment
    assert author != plan


@pytest.mark.parametrize("wf", list(AUTHOR_WORKFLOWS) + list(PLAN_WORKFLOWS),
                         ids=lambda w: w.id)
def test_run_minted_in_the_workflow_experiment_can_be_resumed(tracking, wf):
    """Reproduces the failure: mint where the workflow says, activate the
    same name, resume. Before the fix mcp_svc always minted into
    caldera-mcp-client-1, so the author case raised here."""
    from mlflow.tracking import MlflowClient

    client = MlflowClient()
    exp = mlflow.get_experiment_by_name(wf.mlflow_experiment)
    exp_id = exp.experiment_id if exp else client.create_experiment(wf.mlflow_experiment)
    run_id = client.create_run(experiment_id=exp_id).info.run_id

    # What the workflow does on its first run().
    mlflow.set_experiment(wf.mlflow_experiment)

    mlflow.end_run()
    with mlflow.start_run(run_id=run_id):
        mlflow.set_tag("stage", "initializing")


def test_mismatched_experiment_is_what_raises(tracking):
    """Pins the mechanism, so a future refactor that reintroduces a
    hardcoded name fails here rather than in production."""
    from mlflow.tracking import MlflowClient

    client = MlflowClient()
    minted_in = client.create_experiment("minted-here")
    run_id = client.create_run(experiment_id=minted_in).info.run_id

    mlflow.set_experiment("active-elsewhere")

    mlflow.end_run()
    with pytest.raises(Exception, match="does not match"):
        with mlflow.start_run(run_id=run_id):
            pass
