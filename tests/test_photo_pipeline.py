"""End-to-end photo handling through the real handlers and a scripted LLM
(harness/llm.py) - the classification/label/barcode/dish network calls are staged
in the exact order the pipeline makes them, mirroring the pattern in
tests/test_pipeline_e2e.py. OpenFoodFacts is mocked at the httpx2 layer since it
isn't an LLM call.
"""

from __future__ import annotations

import io

import barcode as barcode_lib
import httpx2 as httpx
from barcode.writer import ImageWriter
from harness.state import create_onboarded_user, food_extraction
from PIL import Image
from sqlalchemy import select

from calobot.persistence.models import FoodEntry
from calobot.persistence.seed import seed_all


def _jpeg_bytes(color=(120, 200, 60)) -> bytes:
    image = Image.new("RGB", (300, 300), color=color)
    out = io.BytesIO()
    image.save(out, format="JPEG")
    return out.getvalue()


def _ean13_png(digits: str) -> bytes:
    code = barcode_lib.get("ean13", digits, writer=ImageWriter())
    out = io.BytesIO()
    code.write(out)
    return out.getvalue()


class _FakeOFFResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeOFFClient:
    def __init__(self, payload, error=None):
        self._payload = payload
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None):
        if self._error is not None:
            raise self._error
        return _FakeOFFResponse(self._payload)


async def test_label_photo_resolves_to_a_food_draft_awaiting_portion(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"kind": "label"},
        {
            "product_name_it": "Barretta ai cereali",
            "energy_value": 430,
            "energy_unit": "kcal",
            "per_portion": False,
            "portion_grams": None,
        },
    )

    sent = await client.send_photo(data=_jpeg_bytes())

    assert "non conservate" in sent[0].text  # first-photo privacy notice
    assert sent[-1].options  # portion clarification, quantity never inferred from a photo

    # "50 grammi" resolves deterministically (food.planner.apply_answer), and the
    # description is already cached under `etichetta` provenance, so no further model
    # call happens here.
    stored = await client.say("50 grammi")

    assert "Registrato" in stored[-1].text
    assert "da etichetta" in stored[-1].text
    db_session.expire_all()
    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    assert entry.grams == 50
    assert entry.kcal_per_100g == 430


async def test_barcode_photo_looks_up_off_and_shows_attribution(db_session, client, llm, monkeypatch):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    payload = {
        "status": 1,
        "product": {"product_name": "Yogurt bianco", "nutriments": {"energy-kcal_100g": 60}},
    }
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeOFFClient(payload))

    llm.push({"kind": "barcode"})

    sent = await client.send_photo(data=_ean13_png("590123412345"))

    assert sent[-1].options

    stored = await client.say("125g")

    assert "Open Food Facts" in stored[-1].text
    assert "ODbL" in stored[-1].text
    db_session.expire_all()
    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    assert entry.kcal_per_100g == 60


async def test_dish_photo_creates_one_draft_per_food_and_abandon_names_what_was_dropped(
    db_session, client, llm
):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"kind": "dish"},
        {
            "items": [
                {"description": "pasta al pomodoro", "preparation": None},
                {"description": "pane", "preparation": None},
            ]
        },
    )

    sent = await client.send_photo(data=_jpeg_bytes())
    assert "pasta al pomodoro" in sent[-1].text

    llm.push(
        {"selected_candidate_id": None},
        {"kcal_per_100g": 158, "display_name_it": "pasta al pomodoro"},
    )
    after_first = await client.say("200 grammi")
    db_session.expire_all()
    assert (await db_session.execute(select(FoodEntry))).scalars().one()  # first food stored
    assert "pane" in after_first[-1].text  # now asking about the second food

    abandoned = await client.tap("❌ lascia perdere")
    assert "pane" in abandoned[-1].text
    assert "niente" not in abandoned[-1].text  # must not claim nothing was recorded

    db_session.expire_all()
    entries = list((await db_session.execute(select(FoodEntry))).scalars())
    assert len(entries) == 1  # pasta stored, pane abandoned before a quantity was known


async def test_unrecognizable_photo_stores_nothing(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push({"kind": "unrecognizable"})

    sent = await client.send_photo(data=_jpeg_bytes())

    assert "Non ho riconosciuto" in sent[-1].text
    db_session.expire_all()
    assert list((await db_session.execute(select(FoodEntry))).scalars()) == []


async def test_privacy_notice_is_shown_only_once(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push({"kind": "unrecognizable"}, {"kind": "unrecognizable"})

    first = await client.send_photo(data=_jpeg_bytes())
    second = await client.send_photo(data=_jpeg_bytes())

    assert "non conservate" in first[-1].text
    assert "non conservate" not in second[-1].text


async def test_unprocessable_file_is_rejected_without_any_model_call(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    sent = await client.send_photo(data=b"not an image at all")

    assert "prova con un'altra foto" in sent[-1].text
    assert llm.calls == []


async def test_no_file_is_written_to_disk_while_handling_a_photo(db_session, client, llm, monkeypatch):
    """tasks.md 1.6: images are processed and discarded, never persisted (design.md -
    Images are processed and discarded). Guards it at runtime by failing loudly if
    anything in the photo path opens a file for writing, on both the success and the
    error path."""
    import builtins

    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if "w" in mode or "a" in mode or "x" in mode:
            raise AssertionError(f"attempted to open {file!r} for writing during photo handling")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)

    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)
    llm.push({"kind": "unrecognizable"})
    await client.send_photo(data=_jpeg_bytes())
    await client.send_photo(data=b"not an image at all")  # the error path too


async def test_illegible_label_asks_for_a_clearer_photo_and_stores_nothing(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push({"kind": "label"}, {"product_name_it": None, "energy_value": None})

    sent = await client.send_photo(data=_jpeg_bytes())

    assert "Non sono riuscito a leggere l'etichetta" in sent[-1].text
    db_session.expire_all()
    assert list((await db_session.execute(select(FoodEntry))).scalars()) == []


async def test_barcode_photo_with_undecodable_code_asks_for_a_clearer_photo(db_session, client, llm):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push({"kind": "barcode"})

    # A plain photo with no actual barcode in it: the classifier (scripted here)
    # says "barcode", but zbar finds nothing to decode.
    sent = await client.send_photo(data=_jpeg_bytes())

    assert "Non sono riuscito a leggere il codice a barre" in sent[-1].text
    db_session.expire_all()
    assert list((await db_session.execute(select(FoodEntry))).scalars()) == []


async def test_barcode_unavailable_service_stores_nothing(db_session, client, llm, monkeypatch):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _FakeOFFClient(None, error=httpx.TimeoutException("slow")),
    )
    llm.push({"kind": "barcode"})

    sent = await client.send_photo(data=_ean13_png("590123412345"))

    assert "temporaneamente non disponibile" in sent[-1].text
    db_session.expire_all()
    assert list((await db_session.execute(select(FoodEntry))).scalars()) == []


async def test_barcode_unknown_product_suggests_the_label_path(db_session, client, llm, monkeypatch):
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeOFFClient({"status": 0}))
    llm.push({"kind": "barcode"})

    sent = await client.send_photo(data=_ean13_png("590123412345"))

    assert "non ho trovato questo prodotto" in sent[-1].text.lower()
    db_session.expire_all()
    assert list((await db_session.execute(select(FoodEntry))).scalars()) == []


async def test_previously_photographed_label_resolves_a_later_typed_mention(db_session, client, llm):
    """tasks.md 6.4: a user who photographs a label once has taught the system that
    product permanently - every later typed mention resolves from the cache with
    label-grade accuracy, at no further model cost for the energy value."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push(
        {"kind": "label"},
        {
            "product_name_it": "Barretta ai cereali",
            "energy_value": 430,
            "energy_unit": "kcal",
            "per_portion": False,
            "portion_grams": None,
        },
    )
    await client.send_photo(data=_jpeg_bytes())
    await client.say("50 grammi")

    llm.push(
        {"intent": "food", "ignored_text": None},
        food_extraction(description="barretta ai cereali", quantity_grams=80),
    )
    stored = await client.say("ho mangiato barretta ai cereali, 80g")

    assert "da etichetta" in stored[-1].text
    db_session.expire_all()
    entries = list((await db_session.execute(select(FoodEntry))).scalars())
    assert len(entries) == 2
    assert entries[-1].kcal_per_100g == 430
    assert entries[-1].provenance.value == "etichetta"


async def test_a_photo_derived_entry_is_corrected_without_another_photo(db_session, client, llm):
    """tasks.md 5.5: a misidentified photo-derived food is corrected exactly like a
    typed one - no re-photographing required."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push({"kind": "label"}, {"product_name_it": "Barretta", "energy_value": 430})
    await client.send_photo(data=_jpeg_bytes())
    confirmation = (await client.say("50 grammi"))[-1]

    corrected = await client.reply_to(confirmation, "no erano 70g")

    assert "70g" in corrected[-1].text
    db_session.expire_all()
    entry = (await db_session.execute(select(FoodEntry))).scalars().one()
    assert entry.grams == 70


async def test_a_photo_derived_entry_appears_in_reports_like_a_typed_one(db_session, client, llm):
    """tasks.md 8.3: a photo-derived entry is an ordinary FoodEntry row, so it must
    show up in a report exactly as a typed entry would."""
    await seed_all(db_session)
    await create_onboarded_user(db_session, 42)

    llm.push({"kind": "label"}, {"product_name_it": "Barretta", "energy_value": 430})
    await client.send_photo(data=_jpeg_bytes())
    await client.say("50 grammi")

    llm.push({"intent": "report", "ignored_text": None}, {"period_text": "oggi", "topic": "food"})
    sent = await client.say("quante calorie ho mangiato oggi?")

    assert "215 kcal" in sent[-1].text  # 430 kcal/100g * 50g
