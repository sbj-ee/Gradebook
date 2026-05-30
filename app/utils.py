"""Grade computation helpers.

These are pure functions — no database, no Flask — so the weighting rules can be
unit-tested in isolation (see tests/test_utils.py) and reused by both the web and
API layers via ``app/models.py``.

A course splits work into three categories whose weights are whole percentages
summing to 100. A student's grade in a category is the percentage of points they
earned across the assignments they were graded on; the final grade is the
weighted average of the categories that actually have grades. Categories with no
graded work are dropped and the remaining weights are renormalized, so an empty
category never silently counts as a zero.
"""

# Canonical category keys, in display order, and their human-friendly labels.
CATEGORIES = ("homework", "quiz", "exam")
CATEGORY_LABELS = {
    "homework": "Homework",
    "quiz": "Quizzes",
    "exam": "Exams",
}

# Supported letter-grade scales.
GRADING_SCALES = ("standard", "plus_minus")
GRADING_SCALE_LABELS = {
    "standard": "Standard (A B C D F)",
    "plus_minus": "Plus / minus (A+ A A- …)",
}

# (cutoff, letter) pairs in descending order for the plus/minus scale.
_PLUS_MINUS = (
    (97, "A+"), (93, "A"), (90, "A-"),
    (87, "B+"), (83, "B"), (80, "B-"),
    (77, "C+"), (73, "C"), (70, "C-"),
    (67, "D+"), (63, "D"), (60, "D-"),
)


def category_percentage(earned, possible):
    """Percentage earned in a category, or None when nothing has been graded."""
    if not possible:
        return None
    return round(earned / possible * 100, 2)


def weighted_final(category_pcts, weights):
    """Weighted final percentage across categories that have a grade.

    ``category_pcts`` maps a category to its percentage (or None) and ``weights``
    maps a category to its whole-percentage weight. Categories whose percentage is
    None are excluded and the surviving weights are renormalized. Returns None when
    no category has a grade.
    """
    total_weight = 0
    accumulated = 0.0
    for category in CATEGORIES:
        pct = category_pcts.get(category)
        if pct is None:
            continue
        weight = weights.get(category, 0)
        accumulated += pct * weight
        total_weight += weight
    if total_weight == 0:
        return None
    return round(accumulated / total_weight, 2)


def letter_grade(pct, scale="standard"):
    """Map a percentage to a letter grade for the given scale. None (no grades)
    renders as an em dash."""
    if pct is None:
        return "—"
    if scale == "plus_minus":
        for cutoff, letter in _PLUS_MINUS:
            if pct >= cutoff:
                return letter
        return "F"
    if pct >= 90:
        return "A"
    if pct >= 80:
        return "B"
    if pct >= 70:
        return "C"
    if pct >= 60:
        return "D"
    return "F"


def parse_weights(homework, quiz, exam):
    """Coerce three weight inputs to ints. Raises ValueError on non-integers."""
    try:
        return int(homework), int(quiz), int(exam)
    except (TypeError, ValueError):
        raise ValueError("weights must be whole numbers") from None
