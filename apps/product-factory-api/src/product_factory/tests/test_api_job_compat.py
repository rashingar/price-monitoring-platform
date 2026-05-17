from __future__ import annotations


def test_api_job_runtime_import_paths_remain_compatible() -> None:
    from product_factory.api.job_models import JobRecord as ApiJobRecord
    from product_factory.api.job_runner import SequentialJobRunner as ApiSequentialJobRunner
    from product_factory.api.job_store import JobStore as ApiJobStore
    from product_factory.jobs.models import JobRecord
    from product_factory.jobs.runner import SequentialJobRunner
    from product_factory.jobs.store import JobStore as RuntimeJobStore

    assert ApiJobRecord is JobRecord
    assert ApiSequentialJobRunner is SequentialJobRunner
    assert ApiJobStore is RuntimeJobStore
