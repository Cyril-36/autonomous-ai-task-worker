from worker.contracts import NetworkAllowance
from worker.tools.network_guard import NetworkGuard


def allowance():
    return NetworkAllowance(run_id="r1", mutation_id="m1", method="POST",
                            url="http://127.0.0.1:8102/invoices",
                            body={"form_token": "t1", "amount": "48250.00"})


def test_guard_blocks_offsite_probe_and_ungated_write():
    guard = NetworkGuard("r1", {"http://127.0.0.1:8101", "http://127.0.0.1:8102"})
    assert not guard.permit("GET", "https://other.example/", "", "")
    assert not guard.permit("GET", "http://127.0.0.1:8102/api/invoices", "", "")
    assert not guard.permit("POST", allowance().url, "application/x-www-form-urlencoded",
                            "form_token=t1&amount=48250.00")


def test_guard_exact_one_shot_body_binding():
    guard = NetworkGuard("r1", {"http://127.0.0.1:8102"})
    expected = allowance()
    guard.arm(expected)
    url = expected.url
    kind = "application/x-www-form-urlencoded"
    assert not guard.permit("POST", url, kind, "form_token=t1&amount=48250.00&extra=x")
    assert not guard.permit("POST", url, kind, "form_token=t1&amount=100.00")
    assert not guard.permit("POST", url, kind, "amount=48250.00")
    assert guard.permit("POST", url, kind, "amount=48250.00&form_token=t1")
    assert not guard.permit("POST", url, kind, "amount=48250.00&form_token=t1")


def test_guard_rejects_duplicate_keys_and_wrong_run():
    guard = NetworkGuard("r2", {"http://127.0.0.1:8102"})
    import pytest

    with pytest.raises(ValueError):
        guard.arm(allowance())
    guard = NetworkGuard("r1", {"http://127.0.0.1:8102"})
    guard.arm(allowance())
    assert not guard.permit("POST", allowance().url, "application/x-www-form-urlencoded",
                            "form_token=t1&amount=48250.00&amount=48250.00")
