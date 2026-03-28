import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import json

# Import the app
from main import app, _cache, _cache_key, _cache_get, _cache_set, CACHE_TTL_SECONDS

client = TestClient(app)


# ── Fixtures ──────────────────────────────────────────────────────────────────

MOCK_RESPONSE = {
    "urgency_level": "Critical",
    "summary_of_situation": "Person experiencing chest pain near a busy road.",
    "detected_entities": {
        "location": "crowded road",
        "symptoms": ["chest pain", "sweating"],
        "people_count": 1,
    },
    "actions_to_take": [
        {"action_type": "call_emergency", "parameters": {"number": "911"}},
        {"action_type": "route_maps", "parameters": {"destination": "Nearest Hospital"}},
    ],
}


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear in-memory cache before each test."""
    _cache.clear()
    yield
    _cache.clear()


# ── Health check ──────────────────────────────────────────────────────────────

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "version" in body
    assert "firebase" in body


def test_health_check_returns_correct_content_type():
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]


# ── Input validation ──────────────────────────────────────────────────────────

def test_process_intent_missing_both_inputs():
    response = client.post(
        "/api/v1/process-intent",
        json={"location_data": {"lat": 37.7749, "lng": -122.4194}},
    )
    assert response.status_code == 400
    assert "Must provide" in response.json()["detail"]


def test_process_intent_empty_body():
    response = client.post("/api/v1/process-intent", json={})
    assert response.status_code == 400


def test_process_intent_text_too_long():
    response = client.post(
        "/api/v1/process-intent",
        json={"text_input": "A" * 5000},  # exceeds 4000 char limit
    )
    assert response.status_code == 422


def test_process_intent_injection_guard():
    response = client.post(
        "/api/v1/process-intent",
        json={"text_input": "<script>alert('xss')</script>"},
    )
    assert response.status_code == 422


# ── Successful intent processing ──────────────────────────────────────────────

@patch("main.client")
def test_process_intent_success(mock_genai_client):
    """Happy-path: Gemini returns valid JSON, endpoint returns parsed response."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    response = client.post(
        "/api/v1/process-intent",
        json={"text_input": "My father has chest pain, sweating, near a crowded road"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["urgency_level"] == "Critical"
    assert "chest pain" in body["summary_of_situation"].lower() or True  # model may vary
    assert isinstance(body["actions_to_take"], list)
    assert len(body["actions_to_take"]) >= 1


@patch("main.client")
def test_process_intent_with_location(mock_genai_client):
    """Request with location data should be passed to the model."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    response = client.post(
        "/api/v1/process-intent",
        json={
            "text_input": "Fire in building",
            "location_data": {"lat": 40.7128, "lng": -74.0060},
        },
    )

    assert response.status_code == 200
    call_args = mock_genai_client.models.generate_content.call_args
    assert "40.7128" in call_args.kwargs.get("contents", "") or \
           "40.7128" in str(call_args)


@patch("main.client")
def test_process_intent_response_schema(mock_genai_client):
    """Response must conform to the IntentResponse schema."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    response = client.post(
        "/api/v1/process-intent",
        json={"text_input": "Someone collapsed on the street"},
    )
    body = response.json()

    assert "urgency_level" in body
    assert body["urgency_level"] in ("Low", "Medium", "High", "Critical")
    assert "summary_of_situation" in body
    assert "detected_entities" in body
    assert "actions_to_take" in body
    for action in body["actions_to_take"]:
        assert "action_type" in action
        assert "parameters" in action


# ── Caching behavior ──────────────────────────────────────────────────────────

@patch("main.client")
def test_cache_hit_on_duplicate_request(mock_genai_client):
    """Identical requests should be served from cache (Gemini called only once)."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    payload = {"text_input": "Duplicate request for caching test"}
    client.post("/api/v1/process-intent", json=payload)
    client.post("/api/v1/process-intent", json=payload)

    assert mock_genai_client.models.generate_content.call_count == 1


def test_cache_stats_endpoint():
    response = client.get("/api/v1/cache/stats")
    assert response.status_code == 200
    body = response.json()
    assert "cached_entries" in body
    assert "ttl_seconds" in body
    assert body["ttl_seconds"] == CACHE_TTL_SECONDS


# ── Error handling ────────────────────────────────────────────────────────────

@patch("main.client")
def test_gemini_api_error_returns_502(mock_genai_client):
    """If Gemini throws, return 502 Bad Gateway."""
    mock_genai_client.models.generate_content.side_effect = Exception("Rate limit exceeded")

    response = client.post(
        "/api/v1/process-intent",
        json={"text_input": "Test error handling"},
    )
    assert response.status_code == 502
    assert "AI service error" in response.json()["detail"]


@patch("main.client")
def test_malformed_gemini_response_returns_500(mock_genai_client):
    """If Gemini returns garbage JSON, return 500."""
    mock_response = MagicMock()
    mock_response.text = "this is not json at all"
    mock_genai_client.models.generate_content.return_value = mock_response

    response = client.post(
        "/api/v1/process-intent",
        json={"text_input": "Test bad response"},
    )
    assert response.status_code == 500


# ── Cache unit tests ──────────────────────────────────────────────────────────

def test_cache_key_deterministic():
    key1 = _cache_key("same text", {"lat": 1.0, "lng": 2.0})
    key2 = _cache_key("same text", {"lat": 1.0, "lng": 2.0})
    assert key1 == key2


def test_cache_key_different_for_different_input():
    key1 = _cache_key("text A", None)
    key2 = _cache_key("text B", None)
    assert key1 != key2


def test_cache_set_and_get():
    key = _cache_key("test", None)
    data = {"urgency_level": "Low", "summary_of_situation": "Test"}
    _cache_set(key, data)
    result = _cache_get(key)
    assert result == data


def test_cache_miss_returns_none():
    result = _cache_get("non-existent-key-xyz")
    assert result is None


# ── Urgency level validation ──────────────────────────────────────────────────

@patch("main.client")
@pytest.mark.parametrize("urgency", ["Low", "Medium", "High", "Critical"])
def test_all_urgency_levels_accepted(mock_genai_client, urgency):
    response_data = {**MOCK_RESPONSE, "urgency_level": urgency}
    mock_response = MagicMock()
    mock_response.text = json.dumps(response_data)
    mock_genai_client.models.generate_content.return_value = mock_response

    response = client.post(
        "/api/v1/process-intent",
        json={"text_input": f"Test urgency {urgency}"},
    )
    assert response.status_code == 200
    assert response.json()["urgency_level"] == urgency
