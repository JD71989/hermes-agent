"""Focused regression tests for Guardian Economic Kernel idempotency."""
from hermes_cli.guardian_economic import EconomicDecision, EconomicKernel


def test_create_job_reuses_idempotency_key_while_pending(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    kernel = EconomicKernel()

    first = kernel.create_job(35, 350, idempotency_key="bond-lead-001")
    second = kernel.create_job(35, 350, idempotency_key="bond-lead-001")

    assert second.job_id == first.job_id
    assert len(kernel.jobs) == 1


def test_create_job_reuses_idempotency_key_after_completion(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    kernel = EconomicKernel()

    first = kernel.create_job(35, 350, idempotency_key="bond-lead-002")
    assert kernel.complete_job(first.job_id, EconomicDecision.ALLOW)

    second = kernel.create_job(35, 350, idempotency_key="bond-lead-002")

    assert second.job_id == first.job_id
    assert len(kernel.jobs) == 1
