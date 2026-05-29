import pytest

from app.utils import (
    category_percentage,
    letter_grade,
    parse_weights,
    weighted_final,
)


def test_category_percentage():
    assert category_percentage(45, 50) == 90.0
    assert category_percentage(0, 50) == 0.0


def test_category_percentage_no_possible_is_none():
    assert category_percentage(0, 0) is None


def test_weighted_final_basic():
    # 90 HW @40, 80 quiz @20, 70 exam @40  ->  (90*40 + 80*20 + 70*40)/100 = 80
    pcts = {"homework": 90.0, "quiz": 80.0, "exam": 70.0}
    weights = {"homework": 40, "quiz": 20, "exam": 40}
    assert weighted_final(pcts, weights) == 80.0


def test_weighted_final_renormalizes_missing_category():
    # Only homework graded -> final equals the homework percentage regardless of weight.
    pcts = {"homework": 85.0, "quiz": None, "exam": None}
    weights = {"homework": 40, "quiz": 20, "exam": 40}
    assert weighted_final(pcts, weights) == 85.0


def test_weighted_final_partial_categories():
    # HW 100 @40 and exam 50 @40 (no quizzes) -> (100*40 + 50*40)/80 = 75
    pcts = {"homework": 100.0, "quiz": None, "exam": 50.0}
    weights = {"homework": 40, "quiz": 20, "exam": 40}
    assert weighted_final(pcts, weights) == 75.0


def test_weighted_final_no_grades_is_none():
    pcts = {"homework": None, "quiz": None, "exam": None}
    weights = {"homework": 40, "quiz": 20, "exam": 40}
    assert weighted_final(pcts, weights) is None


@pytest.mark.parametrize(
    "pct,letter",
    [(95, "A"), (90, "A"), (89.99, "B"), (80, "B"), (70, "C"), (65, "D"), (59, "F")],
)
def test_letter_grade(pct, letter):
    assert letter_grade(pct) == letter


def test_letter_grade_none():
    assert letter_grade(None) == "—"


def test_parse_weights_rejects_non_integers():
    with pytest.raises(ValueError):
        parse_weights("a", 20, 40)
