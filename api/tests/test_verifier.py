import pytest

from travelin.ai.schemas import Candidate
from travelin.ai.summarizer import parse_summary
from travelin.ai.verifier import best_match, haversine_km, name_score, normalize

YOGYAKARTA = {"name": "Yogyakarta", "lat": -7.7956, "lng": 110.3695}


def result(name: str, lat: float, lng: float) -> dict:
    return {
        "id": name.lower().replace(" ", "-"),
        "displayName": {"text": name},
        "location": {"latitude": lat, "longitude": lng},
    }


def test_normalize_strips_accents_and_punctuation():
    assert normalize("Café Lóco & Co.") == "cafe loco co"


def test_name_score_tolerates_extra_words():
    assert name_score("Taman Sari", "Taman Sari Water Castle") == 100
    assert name_score("Gudeg Yu Djum", "Pantai Parangtritis") < 40


def test_haversine_jakarta_to_yogyakarta():
    assert haversine_km(-6.2088, 106.8456, -7.7956, 110.3695) == pytest.approx(430, abs=15)


def test_best_match_picks_the_closest_name_nearby():
    candidate = Candidate(name="Taman Sari", confidence=0.9)
    results = [result("Taman Pintar", -7.80, 110.37), result("Taman Sari", -7.81, 110.36)]
    match, score, _ = best_match(candidate, results, YOGYAKARTA)
    assert match["displayName"]["text"] == "Taman Sari"
    assert score == 100


def test_best_match_ignores_places_far_from_destination():
    candidate = Candidate(name="Taman Sari", confidence=0.9)
    match, _, reason = best_match(candidate, [result("Taman Sari", -6.2, 106.8)], YOGYAKARTA)
    assert match is None
    assert reason == "too far from Yogyakarta"


def test_best_match_without_results():
    match, _, reason = best_match(Candidate(name="Nowhere"), [], YOGYAKARTA)
    assert match is None
    assert reason == "not found on Google Maps"


def test_parse_summary_reads_fenced_json():
    text = 'Here you go:\n```json\n{"highlights": ["Calm pools"], "best_time": "Mornings"}\n```'
    summary = parse_summary(text)
    assert summary is not None
    assert summary.highlights == ["Calm pools"]
    assert summary.best_time == "Mornings"
    assert summary.price_note == ""


def test_parse_summary_rejects_text_without_json():
    assert parse_summary("Sorry, I could not find that place.") is None
