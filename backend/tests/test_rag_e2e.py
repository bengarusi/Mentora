"""Do a student's own uploads actually reach the tutor, and only the right ones?

test_rag_quality.py already holds the retriever to a quality bar in isolation.
This file asks the question one level up, over HTTP: upload a file, start a
lesson, talk to the tutor — did the material make it into the prompt, and did
the unrelated ones stay out?

The two failures worth catching are opposites, and both look fine in a smoke
test: the tutor never seeing the worksheet the student uploaded for this very
lesson, and the tutor being handed last term's geometry handout during a
fractions lesson.
"""

import pytest

from app.api.dependencies import get_llm, get_storage, get_voice_service
from app.files.storage import LocalFileStorage
from app.llm.provider import TutorContext
from app.main import app
from tests.conftest import auth_headers
from tests.fake_llm import FakeLLMProvider

FRACTIONS = (
    "Fractions Worksheet\n"
    "A fraction shows parts of a whole. The top number is the numerator and the "
    "bottom number is the denominator.\n"
    "To add fractions with the same denominator, add the numerators and keep the "
    "denominator the same.\n"
    "Equivalent fractions have the same value: one half equals two quarters.\n"
    "To compare fractions, give them a common denominator first."
)

TIMES_TABLES = (
    "Multiplication and Division\n"
    "Multiplication is repeated addition. 4 times 3 means adding 4 three times, "
    "which is 12.\n"
    "To multiply by 10, add a zero to the end of the number.\n"
    "Division shares a number into equal groups.\n"
    "Learn your times tables by heart."
)

GEOMETRY = (
    "Geometry Notes\n"
    "The perimeter is the total distance around the outside of a shape. To find "
    "the perimeter of a rectangle, add all four sides.\n"
    "The area of a rectangle is length times width.\n"
    "An angle is formed where two lines meet. A right angle is exactly 90 degrees."
)


class RecordingLLM(FakeLLMProvider):
    """Captures every context the tutor was actually given.

    Asserting on the reply would only tell us what a fake chose to say; the
    honest question is what reached the model."""

    def __init__(self):
        super().__init__()
        self.contexts: list[TutorContext] = []

    def _record(self, ctx: TutorContext) -> None:
        self.contexts.append(ctx)

    def generate_teaching_intro(self, ctx, *a, **k):
        self._record(ctx)
        return super().generate_teaching_intro(ctx, *a, **k)

    def chat_reply(self, ctx, *a, **k):
        self._record(ctx)
        return super().chat_reply(ctx, *a, **k)

    def chat_reply_stream(self, ctx, *a, **k):
        self._record(ctx)
        return super().chat_reply_stream(ctx, *a, **k)

    def generate_board_explanation(self, system: str, user: str) -> dict:
        # This one is handed a prepared prompt rather than a context, so the
        # honest question is whether the material made it into the string.
        self.board_prompts.append((system, user))
        return super().generate_board_explanation(system, user)

    def generate_practice_questions(self, ctx, *a, **k):
        self._record(ctx)
        return super().generate_practice_questions(ctx, *a, **k)

    def generate_pre_practice_example(self, ctx, *a, **k):
        self._record(ctx)
        return super().generate_pre_practice_example(ctx, *a, **k)

    @property
    def last(self) -> TutorContext:
        return self.contexts[-1]

    def titles_seen(self) -> list[str]:
        return [e.title for e in self.last.material_excerpts]


@pytest.fixture
def llm():
    recorder = RecordingLLM()
    app.dependency_overrides[get_llm] = lambda: recorder
    yield recorder
    app.dependency_overrides.pop(get_llm, None)


class FakeVoice:
    """No OpenAI calls; the transports under test only need audio to exist."""

    def transcribe_audio(
        self, audio_bytes: bytes, filename: str, context: str | None = None
    ) -> str:
        return "how do I add fractions with the same denominator?"

    def synthesize_speech(self, text: str) -> str:
        return "ZmFrZS1tcDM="

    def chunk_for_speech(self, text: str):
        return [text]


@pytest.fixture
def voice():
    fake = FakeVoice()
    app.dependency_overrides[get_voice_service] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_voice_service, None)


@pytest.fixture
def api(client, tmp_path):
    app.dependency_overrides[get_storage] = lambda: LocalFileStorage(tmp_path)
    yield client
    app.dependency_overrides.pop(get_storage, None)


def _upload(api, headers, *, filename, text, topic, subject="math") -> dict:
    response = api.post(
        "/materials/",
        files={"file": (filename, text.encode(), "text/plain")},
        data={"subject": subject, "topic": topic},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "ready", f"{filename} was not readable: {body}"
    assert body["chunk_count"] > 0
    return body


def _start_lesson(api, headers, *, topic, subtopic, goal) -> int:
    session = api.post(
        "/sessions/",
        json={"subject": "math", "topic": topic, "subtopic": subtopic, "goal_text": goal},
        headers=headers,
    )
    assert session.status_code == 200, session.text
    return session.json()["id"]


def _library(api, headers) -> None:
    """One handout per topic, the way a student's folder actually looks."""
    _upload(api, headers, filename="fractions.txt", text=FRACTIONS, topic="Fractions")
    _upload(api, headers, filename="geometry.txt", text=GEOMETRY, topic="Geometry")


# ---- the material reaches the tutor ----------------------------------------

def test_the_tutor_is_given_the_students_own_worksheet_for_this_topic(api, llm):
    headers = auth_headers(api)
    _library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions with the same denominator.",
    )

    turn = api.post(
        f"/tutor/{sid}/turn",
        json={"content": "how do I add fractions with the same denominator?"},
        headers=headers,
    )

    assert turn.status_code == 200, turn.text
    assert llm.titles_seen() == ["fractions.txt"]
    assert "denominator" in llm.last.material_excerpts[0].content


def test_the_geometry_handout_stays_out_of_a_fractions_lesson(api, llm):
    headers = auth_headers(api)
    _library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Comparing fractions",
        goal="I want to compare fractions.",
    )

    api.post(
        f"/tutor/{sid}/turn",
        json={"content": "how do I compare two fractions?"},
        headers=headers,
    )

    assert "geometry.txt" not in llm.titles_seen()


def test_the_fractions_handout_stays_out_of_a_geometry_lesson(api, llm):
    """The mirror image, so a pass cannot be an artefact of which file won."""
    headers = auth_headers(api)
    _library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Geometry", subtopic="Perimeter",
        goal="I want to find the perimeter of a rectangle.",
    )

    api.post(
        f"/tutor/{sid}/turn",
        json={"content": "how do I find the perimeter of a rectangle?"},
        headers=headers,
    )

    assert llm.titles_seen() == ["geometry.txt"]


def test_a_question_the_library_cannot_answer_retrieves_nothing(api, llm):
    """Retrieval must be able to decline. Handing over the closest file
    regardless is how a tutor ends up teaching from the wrong handout."""
    headers = auth_headers(api)
    _library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )

    api.post(
        f"/tutor/{sid}/turn",
        json={"content": "what did we do in the lesson yesterday?"},
        headers=headers,
    )

    assert llm.titles_seen() == []


def test_small_talk_does_not_drag_in_a_worksheet(api, llm):
    headers = auth_headers(api)
    _library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )

    api.post(f"/tutor/{sid}/turn", json={"content": "ok thanks!"}, headers=headers)

    assert llm.titles_seen() == []


def test_another_students_material_is_never_retrieved(api, llm):
    """Retrieval is scoped by student_id; this is the test that says so out loud."""
    owner = auth_headers(api)
    _library(api, owner)
    other = auth_headers(api, email="someone-else@example.com")
    sid = _start_lesson(
        api, other, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )

    api.post(
        f"/tutor/{sid}/turn",
        json={"content": "how do I add fractions with the same denominator?"},
        headers=other,
    )

    assert llm.titles_seen() == []


def test_an_untagged_upload_is_still_found_when_it_matches(api, llm):
    """Students do not reliably tag their files. An untagged handout that plainly
    talks about the lesson must not be invisible."""
    headers = auth_headers(api)
    api.post(
        "/materials/",
        files={"file": ("notes.txt", FRACTIONS.encode(), "text/plain")},
        data={"subject": "math"},
        headers=headers,
    )
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )

    api.post(
        f"/tutor/{sid}/turn",
        json={"content": "how do I add fractions with the same denominator?"},
        headers=headers,
    )

    assert llm.titles_seen() == ["notes.txt"]


def test_a_deleted_material_stops_reaching_the_tutor(api, llm):
    headers = auth_headers(api)
    material = _upload(
        api, headers, filename="fractions.txt", text=FRACTIONS, topic="Fractions"
    )
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )
    question = {"content": "how do I add fractions with the same denominator?"}
    api.post(f"/tutor/{sid}/turn", json=question, headers=headers)
    assert llm.titles_seen() == ["fractions.txt"]

    assert api.delete(f"/materials/{material['id']}", headers=headers).status_code == 204
    api.post(f"/tutor/{sid}/turn", json=question, headers=headers)

    assert llm.titles_seen() == []


# ---- where retrieval does NOT run ------------------------------------------
#
# These document real gaps rather than desired behaviour. Retrieval is driven by
# the student's message, so every tutor output produced without one runs blind
# to the student's library. Written down here so the limits are visible instead
# of being discovered in a lesson.

def test_the_lesson_opening_is_written_without_the_students_material(api, llm):
    """GAP: the opening explanation is generated from the curriculum alone.

    A student who uploads their class handout and starts a lesson on that exact
    topic gets an opening that has never seen it — the material only arrives
    once they ask something."""
    headers = auth_headers(api)
    _library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions with the same denominator.",
    )

    response = api.post(f"/tutor/{sid}/difficulty", json={"level": "easy"}, headers=headers)

    assert response.status_code == 200
    assert llm.titles_seen() == []


def test_practice_questions_are_generated_without_the_students_material(api, llm):
    """GAP: practice is generated from the curriculum alone, so it cannot follow
    the notation or method the student's own class uses."""
    headers = auth_headers(api)
    _library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )
    api.post(f"/tutor/{sid}/difficulty", json={"level": "easy"}, headers=headers)
    api.post(f"/tutor/{sid}/advance", headers=headers)

    api.post(f"/tutor/{sid}/practice/start", headers=headers)

    assert llm.titles_seen() == []


# ---- every way a student message can reach the tutor ------------------------
#
# Retrieval hangs off build_tutor_context(text). Each transport calls it from a
# different place, so any one of them can silently stop passing the message and
# nothing else would look wrong. These pin all of them.

QUESTION = "how do I add fractions with the same denominator?"


def _fractions_lesson(api, headers) -> int:
    _library(api, headers)
    return _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions with the same denominator.",
    )


def test_the_typed_turn_retrieves(api, llm):
    headers = auth_headers(api)
    sid = _fractions_lesson(api, headers)

    api.post(f"/tutor/{sid}/turn", json={"content": QUESTION}, headers=headers)

    assert llm.titles_seen() == ["fractions.txt"]


def test_the_text_stream_retrieves(api, llm):
    headers = auth_headers(api)
    sid = _fractions_lesson(api, headers)

    response = api.post(
        f"/tutor/{sid}/turn/stream", json={"content": QUESTION}, headers=headers
    )

    assert response.status_code == 200
    assert llm.titles_seen() == ["fractions.txt"]


def test_the_speech_stream_retrieves(api, llm, voice):
    headers = auth_headers(api)
    sid = _fractions_lesson(api, headers)

    response = api.post(
        f"/tutor/{sid}/turn/speech-stream", json={"content": QUESTION}, headers=headers
    )

    assert response.status_code == 200
    assert llm.titles_seen() == ["fractions.txt"]


def test_the_voice_turn_retrieves(api, llm, voice):
    """The spoken path transcribes first, so the transcript is what must reach
    retrieval — not an empty query."""
    headers = auth_headers(api)
    sid = _fractions_lesson(api, headers)

    response = api.post(
        f"/tutor/{sid}/voice-turn",
        files={"file": ("q.webm", b"fake-audio", "audio/webm")},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert llm.titles_seen() == ["fractions.txt"]


def test_a_board_request_retrieves(api, llm, monkeypatch):
    """The board is generated from build_tutor_context(focus), so the student's
    own material shapes what gets drawn."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "BOARD_EXPLANATION_ENABLED", True)
    headers = auth_headers(api)
    sid = _fractions_lesson(api, headers)

    response = api.post(
        f"/tutor/{sid}/boards/lesson", json={"focus": QUESTION}, headers=headers
    )

    assert response.status_code == 201, response.text
    _, board_prompt = llm.board_prompts[-1]
    assert "fractions.txt" in board_prompt
    assert "denominator" in board_prompt


def test_the_summary_phase_chat_retrieves(api, llm):
    """Teaching is not the only conversational phase; summary chat must not be
    a blind spot."""
    headers = auth_headers(api)
    sid = _fractions_lesson(api, headers)
    api.post(f"/tutor/{sid}/difficulty", json={"level": "easy"}, headers=headers)
    for _ in range(4):  # teaching -> example -> practice -> results -> summary
        api.post(f"/tutor/{sid}/advance", headers=headers)
    session = api.get(f"/sessions/{sid}", headers=headers).json()
    assert session["phase"] == "summary", session["phase"]

    api.post(f"/tutor/{sid}/turn", json={"content": QUESTION}, headers=headers)

    assert llm.titles_seen() == ["fractions.txt"]


# ---- directions retrieval must refuse --------------------------------------

def test_homework_help_never_reaches_into_the_general_library(api, llm):
    """A homework session's own file is its context. Pulling in the wider
    library would dilute it — and would leak study material into a session
    scoped to one worksheet."""
    headers = auth_headers(api)
    _library(api, headers)
    session = api.post("/tutor/homework", json={"subject": "math"}, headers=headers).json()
    api.post(
        f"/materials/homework/{session['id']}",
        files={"file": ("hw.txt", b"Exercise 1: 1/4 + 1/4", "text/plain")},
        headers=headers,
    )
    api.post(f"/tutor/{session['id']}/homework/analyze", headers=headers)

    api.post(f"/tutor/{session['id']}/turn", json={"content": QUESTION}, headers=headers)

    assert llm.titles_seen() == []


def test_material_from_another_subject_is_not_retrieved(api, llm):
    """Subject is a hard filter, not a ranking hint: an English handout has no
    business in a maths lesson however many words it shares."""
    headers = auth_headers(api)
    api.post(
        "/materials/",
        files={"file": ("english.txt", FRACTIONS.encode(), "text/plain")},
        data={"subject": "english", "topic": "Fractions"},
        headers=headers,
    )
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )

    api.post(f"/tutor/{sid}/turn", json={"content": QUESTION}, headers=headers)

    assert llm.titles_seen() == []


def test_a_material_still_being_processed_is_not_retrieved(api, llm):
    """Only READY material is retrievable; a half-extracted file must not reach
    the tutor as a partial or empty passage."""
    headers = auth_headers(api)
    unreadable = api.post(
        "/materials/",
        files={"file": ("scan.xyz", b"\x00\x01binary", "application/octet-stream")},
        data={"subject": "math", "topic": "Fractions"},
        headers=headers,
    ).json()
    assert unreadable["status"] != "ready"
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )

    api.post(f"/tutor/{sid}/turn", json={"content": QUESTION}, headers=headers)

    assert llm.titles_seen() == []


def test_the_strongest_match_wins_when_two_files_share_a_topic(api, llm):
    """Two handouts on the same topic: the tutor should get the one that answers
    the question, not both competing for its attention."""
    headers = auth_headers(api)
    _upload(api, headers, filename="adding.txt", text=FRACTIONS, topic="Fractions")
    _upload(
        api, headers, filename="shapes_of_fractions.txt", topic="Fractions",
        text=(
            "Fraction Shapes\n"
            "You can show a fraction as a shaded circle or a shaded bar.\n"
            "Colour in the parts to match the fraction shown."
        ),
    )
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )

    api.post(f"/tutor/{sid}/turn", json={"content": QUESTION}, headers=headers)

    assert llm.titles_seen() == ["adding.txt"]


# ---- topic isolation, the direction that actually costs money ---------------
#
# A student's folder fills up over a term. Every handout that reaches a lesson
# it has nothing to do with is prompt budget spent on noise, and a chance for
# the tutor to teach from the wrong page. The fractions handout below contains
# the word "multiply" — as real fractions notes do — which is the overlap most
# likely to bleed into a multiplication lesson.

def _two_topic_library(api, headers) -> None:
    _upload(api, headers, filename="fractions.txt", text=FRACTIONS, topic="Fractions")
    _upload(
        api, headers, filename="times_tables.txt", text=TIMES_TABLES,
        topic="Multiplication & Division",
    )


@pytest.mark.parametrize(
    "question",
    [
        "how do I multiply by 10?",
        "what does 4 times 3 mean?",
        "what happens when I multiply by the same number?",
    ],
)
def test_fractions_material_stays_out_of_a_multiplication_lesson(api, llm, question):
    """The last question is the trap: the fractions handout literally says
    "multiply ... by the same number"."""
    headers = auth_headers(api)
    _two_topic_library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Multiplication & Division", subtopic="Multiplying by 10",
        goal="I want to multiply numbers by 10.",
    )

    api.post(f"/tutor/{sid}/turn", json={"content": question}, headers=headers)

    assert "fractions.txt" not in llm.titles_seen()


@pytest.mark.parametrize(
    "question",
    [
        "how do I add fractions with the same denominator?",
        "what is a numerator?",
        "how do I compare two fractions?",
    ],
)
def test_multiplication_material_stays_out_of_a_fractions_lesson(api, llm, question):
    headers = auth_headers(api)
    _two_topic_library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )

    api.post(f"/tutor/{sid}/turn", json={"content": question}, headers=headers)

    assert "times_tables.txt" not in llm.titles_seen()


def test_a_lesson_topic_with_no_matching_material_gets_nothing(api, llm):
    """A folder full of other topics must not mean the tutor gets the least-bad
    handout. Nothing is the right answer here."""
    headers = auth_headers(api)
    _two_topic_library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Geometry", subtopic="Perimeter",
        goal="I want to find the perimeter of a rectangle.",
    )

    api.post(
        f"/tutor/{sid}/turn",
        json={"content": "how do I find the perimeter of a rectangle?"},
        headers=headers,
    )

    assert llm.titles_seen() == []


def test_the_lessons_own_material_outranks_a_crossing_over_one(api, llm):
    """Off-topic material is penalised, not banned: a student who types
    "numerator" during a multiplication lesson is asking about fractions and
    should get that handout. What must hold is ordering — the lesson's own
    material comes first, so it is the one the tutor leans on."""
    headers = auth_headers(api)
    _two_topic_library(api, headers)
    sid = _start_lesson(
        api, headers, topic="Multiplication & Division", subtopic="Multiplying by 10",
        goal="I want to multiply numbers by 10.",
    )

    api.post(
        f"/tutor/{sid}/turn",
        json={"content": "multiply the numerator and denominator by the same number"},
        headers=headers,
    )

    titles = llm.titles_seen()
    assert titles, "a question this explicit should retrieve something"
    assert titles[0] == "times_tables.txt", f"lesson material must rank first, got {titles}"


def test_retrieval_stays_a_small_share_of_the_prompt(api, llm):
    """The guard against a folder full of handouts crowding out the lesson."""
    headers = auth_headers(api)
    _two_topic_library(api, headers)
    _upload(api, headers, filename="more_fractions.txt", text=FRACTIONS, topic="Fractions")
    sid = _start_lesson(
        api, headers, topic="Fractions", subtopic="Adding fractions",
        goal="I want to add fractions.",
    )

    api.post(
        f"/tutor/{sid}/turn",
        json={"content": "how do I add fractions with the same denominator?"},
        headers=headers,
    )

    injected = sum(len(e.content) for e in llm.last.material_excerpts)
    assert injected <= 4000, "MATERIAL_CONTEXT_CHAR_BUDGET must be respected"
    assert len(llm.last.material_excerpts) <= 3, "top-k caps how many passages compete"
