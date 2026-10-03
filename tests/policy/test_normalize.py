import pytest

from worker.policy.normalize import normalize


@pytest.mark.parametrize(("shown", "expected"), [
    ("₹48,250.00", "48250.00"), ("Rs 1,00,000.00", "100000.00"),
    ("INR 1,234,567.89", "1234567.89"), ("125", "125.00"),
])
def test_amount_normalization(shown, expected):
    assert normalize(shown, "amount") == expected


@pytest.mark.parametrize("shown", ["1,00,00.0", "1,23,45,6.00", "12.345", "-1.00"])
def test_invalid_amounts_are_refused(shown):
    with pytest.raises(ValueError):
        normalize(shown, "amount")


@pytest.mark.parametrize(("shown", "expected"), [
    ("20 Oct 2026", "2026-10-20"), ("20/10/2026", "2026-10-20"),
    ("2026-10-20", "2026-10-20"),
])
def test_date_normalization(shown, expected):
    assert normalize(shown, "date") == expected


def test_invalid_day_first_date_is_refused():
    with pytest.raises(ValueError):
        normalize("31/02/2026", "date")


def test_text_only_trims_whitespace():
    assert normalize("  AB  12  ", "text") == "AB  12"
