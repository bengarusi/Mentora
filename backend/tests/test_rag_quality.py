"""Retrieval quality bar.

These tests exist because the failure mode that matters isn't a crash — it's
the tutor quietly being handed the wrong worksheet, or being buried in
loosely-related passages. Both look fine in a smoke test and ruin a lesson.
"""

import tempfile

import pytest

from app.core.enums import MaterialKind
from app.files.retrieval import KeywordMaterialRetriever
from app.files.storage import LocalFileStorage
from app.services.material_service import MaterialService
from tests.conftest import make_student

# A small but realistic set of class handouts, one per curriculum topic.
CORPUS: dict[str, tuple[str, str]] = {
    "Fractions": (
        "fractions_worksheet.txt",
        "Fractions Worksheet\n"
        "A fraction shows parts of a whole. The top number is the numerator and "
        "the bottom number is the denominator.\n"
        "Equivalent fractions have the same value. To find an equivalent "
        "fraction, multiply the numerator and the denominator by the same "
        "number. For example 1/2 equals 2/4 equals 4/8.\n"
        "To add fractions with the same denominator, add the numerators and keep "
        "the denominator the same.\n"
        "To compare fractions, give them a common denominator first.",
    ),
    "Geometry": (
        "geometry_notes.txt",
        "Geometry Notes\n"
        "The perimeter is the total distance around the outside of a shape. To "
        "find the perimeter of a rectangle, add all four sides.\n"
        "The area is the space inside a shape. The area of a rectangle is length "
        "times width. Area is measured in square units.\n"
        "An angle is formed where two lines meet. A right angle is exactly 90 "
        "degrees. An obtuse angle is larger than 90 degrees.",
    ),
    "Decimals & Percentages": (
        "decimals.txt",
        "Decimals and Percentages\n"
        "A decimal point separates whole numbers from parts. The first digit "
        "after the point is tenths, the second is hundredths.\n"
        "To compare decimals, line up the decimal points.\n"
        "A percentage is a part out of one hundred. 50 percent means 50 out of "
        "100, which is one half.",
    ),
    "Multiplication & Division": (
        "times_tables.txt",
        "Multiplication and Division\n"
        "Multiplication is repeated addition. 4 times 3 means adding 4 three "
        "times, which is 12.\n"
        "Division shares a number into equal groups. 12 divided by 3 means "
        "splitting 12 into 3 equal groups of 4.\n"
        "Learn the times tables by heart.",
    ),
    "Numbers & Place Value": (
        "place_value.txt",
        "Numbers and Place Value\n"
        "Every digit in a number has a place value. In the number 3524, the 3 is "
        "thousands, the 5 is hundreds, the 2 is tens and the 4 is ones.\n"
        "To round a number to the nearest ten, look at the ones digit. If it is "
        "5 or more, round up.",
    ),
    "Measurement": (
        "measurement.txt",
        "Measurement\n"
        "Length is measured in centimetres and metres. There are 100 centimetres "
        "in one metre.\n"
        "Weight is measured in grams and kilograms. There are 1000 grams in one "
        "kilogram.",
    ),
    "Word Problems": (
        "word_problems.txt",
        "Word Problems\n"
        "Read the question carefully and work out what it is asking you to find.\n"
        "Look for clue words. Altogether and total usually mean add. Left over "
        "and difference usually mean subtract.\n"
        "Choose the operation, then check your answer makes sense.",
    ),
    "Addition & Subtraction": (
        "carrying.txt",
        "Addition and Subtraction\n"
        "When adding two digit numbers, line up the columns. If a column adds to "
        "more than 9, carry the ten into the next column.\n"
        "When subtracting, if the top digit is smaller than the bottom digit, "
        "borrow ten from the column to the left.",
    ),
}


def _service(db, tmp_path=None):
    return MaterialService(
        db,
        make_student(db),
        LocalFileStorage(tmp_path or tempfile.mkdtemp()),
        KeywordMaterialRetriever(),
    )


def _upload(svc, name, body, topic=None, kind=MaterialKind.STUDY_MATERIAL):
    return svc.upload_material(
        data=body.encode(),
        filename=name,
        content_type="text/plain",
        kind=kind,
        subject="math",
        topic=topic,
    )


@pytest.fixture
def library(db_session, tmp_path):
    """A student with the full multi-topic corpus uploaded and tagged."""
    svc = _service(db_session, tmp_path)
    for topic, (filename, body) in CORPUS.items():
        _upload(svc, filename, body, topic=topic)
    return svc


# ---------------------------------------------------------------------------
# The right document, for the right lesson
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "topic,question,expected",
    [
        ("Fractions", "how do I find equivalent fractions?", "fractions_worksheet.txt"),
        ("Fractions", "what is a numerator and denominator?", "fractions_worksheet.txt"),
        ("Fractions", "how do I compare two fractions?", "fractions_worksheet.txt"),
        ("Geometry", "what is the perimeter of a rectangle?", "geometry_notes.txt"),
        ("Geometry", "how do I work out the area?", "geometry_notes.txt"),
        ("Geometry", "what is an obtuse angle?", "geometry_notes.txt"),
        ("Decimals & Percentages", "what does percent mean?", "decimals.txt"),
        ("Decimals & Percentages", "how do I compare decimals?", "decimals.txt"),
        ("Numbers & Place Value", "how do I round to the nearest ten?", "place_value.txt"),
        ("Numbers & Place Value", "what is the place value of each digit?", "place_value.txt"),
        ("Measurement", "how many centimetres are in a metre?", "measurement.txt"),
        ("Multiplication & Division", "explain the times tables", "times_tables.txt"),
        ("Multiplication & Division", "what is division?", "times_tables.txt"),
        ("Word Problems", "what clue words mean I should add?", "word_problems.txt"),
        ("Addition & Subtraction", "how does carrying work when adding?", "carrying.txt"),
        ("Addition & Subtraction", "when do I borrow in subtraction?", "carrying.txt"),
    ],
)
def test_retrieves_the_right_document_for_the_lesson(library, topic, question, expected):
    hits = library.retrieve_relevant(query=question, subject="math", topic=topic)
    assert hits, f"nothing retrieved for {question!r}"
    assert hits[0].material_title == expected


@pytest.mark.parametrize(
    "topic,question",
    [
        ("Fractions", "how do I find equivalent fractions?"),
        ("Geometry", "what is the perimeter of a rectangle?"),
        ("Measurement", "how many centimetres are in a metre?"),
        ("Addition & Subtraction", "when do I borrow in subtraction?"),
    ],
)
def test_no_off_topic_documents_come_along_for_the_ride(library, topic, question):
    """The tutor should get the passage that answers the question — not a tail
    of loosely-related ones competing for its attention."""
    hits = library.retrieve_relevant(query=question, subject="math", topic=topic)
    titles = {h.material_title for h in hits}
    expected = CORPUS[topic][0]
    assert titles <= {expected}, f"off-topic material pulled in: {titles - {expected}}"


@pytest.mark.parametrize(
    "question",
    [
        "what is photosynthesis",
        "who won the world cup",
        "hello can you help me",
        "I feel tired today",
        "thanks that makes sense",
        "ok",
        "cool",
    ],
)
def test_irrelevant_messages_retrieve_nothing(library, question):
    """Chit-chat and off-subject questions must not spend prompt budget."""
    assert library.retrieve_relevant(query=question, subject="math", topic="Fractions") == []


# ---------------------------------------------------------------------------
# Behaviour that the precision rules must not break
# ---------------------------------------------------------------------------

def test_untagged_material_is_still_retrievable(db_session, tmp_path):
    """Students won't always tag their uploads; those files must still work."""
    svc = _service(db_session, tmp_path)
    _upload(
        svc,
        "untagged.txt",
        "Equivalent fractions have the same value. Multiply the numerator and "
        "denominator by the same number.",
    )
    hits = svc.retrieve_relevant(
        query="how do I find equivalent fractions?", subject="math", topic="Fractions"
    )
    assert [h.material_title for h in hits] == ["untagged.txt"]


def test_both_documents_on_a_topic_stay_reachable(db_session, tmp_path):
    svc = _service(db_session, tmp_path)
    _upload(
        svc,
        "part1.txt",
        "A fraction has a numerator on top and a denominator on the bottom. The "
        "denominator tells how many equal parts the whole is split into.",
        topic="Fractions",
    )
    _upload(
        svc,
        "part2.txt",
        "Equivalent fractions have the same value. Multiply the numerator and "
        "denominator by the same number to find one.",
        topic="Fractions",
    )
    first = svc.retrieve_relevant(
        query="what does the denominator tell me?", subject="math", topic="Fractions"
    )
    second = svc.retrieve_relevant(
        query="how do I find equivalent fractions?", subject="math", topic="Fractions"
    )
    assert first[0].material_title == "part1.txt"
    assert second[0].material_title == "part2.txt"


def test_strong_cross_topic_match_still_surfaces(db_session, tmp_path):
    """Topic tags guide retrieval; they must not imprison it. A fractions
    question during a word-problems lesson should still find the fractions
    handout."""
    svc = _service(db_session, tmp_path)
    _upload(
        svc,
        "fractions.txt",
        "To add fractions with the same denominator, add the numerators and keep "
        "the denominator the same.",
        topic="Fractions",
    )
    _upload(
        svc,
        "word_problems.txt",
        "Read the question and decide which operation to use. Total means add.",
        topic="Word Problems",
    )
    hits = svc.retrieve_relevant(
        query="how do I add fractions with the same denominator?",
        subject="math",
        topic="Word Problems",
    )
    assert hits[0].material_title == "fractions.txt"


def test_on_topic_material_beats_a_keyword_stuffed_off_topic_file(db_session, tmp_path):
    svc = _service(db_session, tmp_path)
    _upload(
        svc,
        "geometry.txt",
        "The area of a rectangle is length times width. Area is the space inside "
        "a shape.",
        topic="Geometry",
    )
    _upload(
        svc,
        "decoy.txt",
        "Work out the area of the garden. Work out the total. Work out the "
        "difference. Work out the space.",
        topic="Word Problems",
    )
    hits = svc.retrieve_relevant(
        query="how do I work out the area?", subject="math", topic="Geometry"
    )
    assert hits[0].material_title == "geometry.txt"


def test_ranking_is_stable_as_the_library_grows(db_session, tmp_path):
    """Scores are normalised, so adding unrelated files must not change which
    document wins — or push a small library below the relevance threshold."""
    svc = _service(db_session, tmp_path)
    _upload(
        svc,
        "target.txt",
        "Equivalent fractions have the same value. Multiply the numerator and "
        "the denominator by the same number.",
        topic="Fractions",
    )
    question = dict(query="how do I find equivalent fractions?", subject="math", topic="Fractions")
    assert svc.retrieve_relevant(**question)[0].material_title == "target.txt"

    filler = (
        "Practice these questions and show your working in your exercise book. "
    ) * 6
    for i in range(40):
        _upload(svc, f"filler_{i}.txt", f"Handout {i}. {filler}", topic="Measurement")

    hits = svc.retrieve_relevant(**question)
    assert hits and hits[0].material_title == "target.txt"
    assert {h.material_title for h in hits} == {"target.txt"}
