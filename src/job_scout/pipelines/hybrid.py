from job_scout.adapters.registry import iter_adapters
from job_scout.models.enums import PipelineName, WorkMode
from job_scout.models.job import PipelineStats
from job_scout.pipelines.common import run_pipeline
from job_scout.services.database import JobRepository
from job_scout.services.fx import FxService


def run_hybrid_pipeline(repo: JobRepository, fx: FxService | None = None) -> PipelineStats:
    return run_pipeline(
        pipeline=PipelineName.HYBRID,
        adapters=iter_adapters(pipeline="hybrid"),
        repo=repo,
        fx=fx,
        expected_work_mode=WorkMode.HYBRID,
    )
