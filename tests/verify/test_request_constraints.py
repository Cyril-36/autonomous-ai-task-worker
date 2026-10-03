from datetime import date

import pytest

from worker.verify.goals import dates_in, numbers_in


@pytest.mark.parametrize("text,expected", [
    ("Export invoices due before 2026-12-01.", date(2026, 12, 1)),
    ("due before 1 November 2026", date(2026, 11, 1)),
    ("due before 1 Nov 2026", date(2026, 11, 1)),
    ("due before November 1, 2026", date(2026, 11, 1)),
    ("due before 15/11/2026 (day first)", date(2026, 11, 15)),
    ("due before the 15th of November 2026", date(2026, 11, 15)),
])
def test_dates_in_reads_common_written_forms(text, expected):
    assert expected in dates_in(text.casefold())


def test_dates_in_ignores_impossible_dates():
    assert dates_in("due before 31/02/2026") == set()


@pytest.mark.parametrize("text,value", [
    ("at most 5 invoices", 5), ("up to three of them", 3), ("no more than two", 2),
    ("a maximum of ten", 10),
])
def test_numbers_in_reads_digits_and_words(text, value):
    assert value in numbers_in(text)


def test_numbers_in_does_not_invent_numbers():
    assert numbers_in("record every invoice we have not entered") == set()
