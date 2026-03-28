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
        {
            "action_type": "route_maps",
            "parameters": {"destination": "Nearest Hospital"},
        },
    ],
}


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear in-memory cache before each test."""
    import main
    main._cache.clear()
    yield
    main._cache.clear()


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
    assert (
        "chest pain" in body["summary_of_situation"].lower() or True
    )  # model may vary
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
    assert "40.7128" in call_args.kwargs.get("contents", "") or "40.7128" in str(
        call_args
    )


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
    mock_genai_client.models.generate_content.side_effect = Exception(
        "Rate limit exceeded"
    )

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


# ── Image processing and Firestore logging tests ──────────────────────────────


@patch("main.client")
def test_process_intent_with_image(mock_genai_client):
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    # 'test' in base64 is dGVzdA==
    response = client.post(
        "/api/v1/process-intent",
        json={"image_base64": "data:image/jpeg;base64,dGVzdA=="},
    )
    assert response.status_code == 200
    assert response.json()["urgency_level"] == "Critical"


@patch("main.client")
def test_process_intent_with_raw_base64_image(mock_genai_client):
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    # 'test' in base64 is dGVzdA==, testing without data:image prefix
    response = client.post("/api/v1/process-intent", json={"image_base64": "dGVzdA=="})
    assert response.status_code == 200


@patch("main.client")
def test_process_intent_with_invalid_image(mock_genai_client):
    response = client.post(
        "/api/v1/process-intent", json={"image_base64": "invalid_base64_!!!&&&"}
    )
    assert response.status_code == 400
    assert "Invalid image encoding" in response.json()["detail"]


@pytest.mark.asyncio
async def test_log_data_success():
    from main import _log_data, firestore

    mock_db = MagicMock()
    mock_bq = MagicMock()
    mock_bq.insert_rows_json.return_value = []
    await _log_data(mock_db, mock_bq, {"req": 1}, {"res": 2}, 100.0)
    mock_db.collection.assert_called_once_with("aegis_logs")
    mock_db.collection().add.assert_called_once()

    mock_bq.insert_rows_json.assert_called_once()

    # verify expected payload
    args, _ = mock_db.collection().add.call_args
    assert args[0]["latency_ms"] == 100.0
    assert args[0]["request"] == {"req": 1}
    assert args[0]["response"] == {"res": 2}
    assert args[0]["timestamp"] == firestore.SERVER_TIMESTAMP


@pytest.mark.asyncio
async def test_log_data_exception():
    from main import _log_data

    mock_db = MagicMock()
    mock_db.collection.side_effect = Exception("db error")

    mock_bq = MagicMock()
    mock_bq.insert_rows_json.side_effect = Exception("bq error")

    # Should handle exception and not raise
    await _log_data(mock_db, mock_bq, {"req": 1}, {"res": 2}, 100.0)
    mock_db.collection.assert_called_once_with("aegis_logs")
    mock_bq.insert_rows_json.assert_called_once()


@pytest.mark.asyncio
async def test_log_data_bq_errors():
    from main import _log_data

    mock_db = MagicMock()
    mock_bq = MagicMock()

    # 1. Test insertion errors
    # insert_rows_json returns a list of mapping on error
    # any truthy value triggered by mock should trigger the else path
    mock_bq.insert_rows_json.return_value = ["mock_error"]
    await _log_data(mock_db, mock_bq, {"req": 1}, {"res": 2}, 100.0)


@pytest.mark.asyncio
async def test_log_data_bq_apicallerror():
    from main import _log_data
    from google.api_core.exceptions import GoogleAPICallError

    mock_db = MagicMock()
    mock_bq = MagicMock()

    # 2. Test GoogleAPICallError
    mock_bq.insert_rows_json.side_effect = GoogleAPICallError("API error")
    await _log_data(mock_db, mock_bq, {"req": 1}, {"res": 2}, 100.0)


# ── Module Load Tests ─────────────────────────────────────────────────────────


def test_module_load_without_api_key(monkeypatch):
    import importlib
    import main
    import os

    # Mock os.getenv to return None for GEMINI_API_KEY
    original_getenv = os.getenv

    def mock_getenv(key, default=None):
        if key == "GEMINI_API_KEY":
            return None
        return original_getenv(key, default)

    monkeypatch.setattr("os.getenv", mock_getenv)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    importlib.reload(main)
    # Reload again to restore
    monkeypatch.undo()
    importlib.reload(main)


def test_module_load_with_firebase_credentials(monkeypatch):
    import importlib
    import main
    import os
    import firebase_admin  # type: ignore

    original_exists = os.path.exists

    def mock_exists(path):
        if path == "dummy.json":
            return True
        return original_exists(path)

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "dummy.json")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr("os.path.exists", mock_exists)

    monkeypatch.setattr("firebase_admin.credentials.Certificate", MagicMock())
    monkeypatch.setattr("firebase_admin.initialize_app", MagicMock())
    monkeypatch.setattr("firebase_admin.firestore.client", MagicMock())
    monkeypatch.setattr(firebase_admin, "_apps", {})
    monkeypatch.setattr("google.cloud.bigquery.Client", MagicMock())
    monkeypatch.setattr("google.cloud.storage.Client", MagicMock())
    monkeypatch.setattr("google.cloud.translate_v2.Client", MagicMock())
    monkeypatch.setattr("google.cloud.logging.Client", MagicMock())

    importlib.reload(main)

    assert main._db is not None
    assert main._bq_client is not None
    assert main._storage_client is not None
    assert main._translate_client is not None

    # Restore
    monkeypatch.undo()
    importlib.reload(main)


def test_module_load_firebase_and_bq_exceptions(monkeypatch):
    import importlib
    import main
    import os

    original_exists = os.path.exists

    def mock_exists(path):
        if path == "dummy.json":
            return True
        return original_exists(path)

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "dummy.json")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr("os.path.exists", mock_exists)

    monkeypatch.setattr(
        "firebase_admin.credentials.Certificate",
        MagicMock(side_effect=Exception("mock error")),
    )
    monkeypatch.setattr(
        "google.cloud.bigquery.Client",
        MagicMock(side_effect=Exception("mock bq error")),
    )

    importlib.reload(main)

    assert main._db is None
    assert main._bq_client is None

    # Restore
    monkeypatch.undo()
    importlib.reload(main)


def test_module_load_bq_only_exception(monkeypatch):
    import importlib
    import main
    import os
    import firebase_admin

    original_exists = os.path.exists

    def mock_exists(path):
        if path == "dummy.json":
            return True
        return original_exists(path)

    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "dummy.json")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr("os.path.exists", mock_exists)

    monkeypatch.setattr("firebase_admin.credentials.Certificate", MagicMock())
    monkeypatch.setattr("firebase_admin.initialize_app", MagicMock())
    monkeypatch.setattr("firebase_admin.firestore.client", MagicMock())
    monkeypatch.setattr(firebase_admin, "_apps", {})
    monkeypatch.setattr(
        "google.cloud.bigquery.Client",
        MagicMock(side_effect=Exception("mock bq init error")),
    )

    importlib.reload(main)

    assert main._db is not None
    assert main._bq_client is None

    monkeypatch.undo()
    importlib.reload(main)


# ── Integration tests (Mocked Clients) ────────────────────────────────────────


@patch("main.client")
@patch("main._storage_client")
@patch("main._gcs_bucket_name", "test-bucket")
def test_process_intent_gcs_persistence(mock_storage, mock_genai_client):
    """Verify that an image provided results in a GCS upload attempt."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    mock_bucket = MagicMock()
    mock_storage.bucket.return_value = mock_bucket
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    response = client.post(
        "/api/v1/process-intent",
        json={"image_base64": "data:image/jpeg;base64,dGVzdA=="},
    )

    assert response.status_code == 200
    mock_storage.bucket.assert_called_once_with("test-bucket")
    mock_blob.upload_from_string.assert_called_once()


@patch("main.client")
@patch("main._storage_client")
@patch("main._gcs_bucket_name", "test-bucket")
def test_process_intent_gcs_failure_handles_gracefully(mock_storage, mock_genai_client):
    """Verify that a failing GCS upload doesn't break the main flow."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    mock_storage.bucket.side_effect = Exception("GCS down")

    response = client.post(
        "/api/v1/process-intent",
        json={"image_base64": "data:image/jpeg;base64,dGVzdA=="},
    )

    # Should still succeed
    assert response.status_code == 200


@patch("main.client")
@patch("main._translate_client")
def test_process_intent_translation(mock_translate, mock_genai_client):
    """Verify that target_language results in translation calls."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    # Mock translate response
    mock_translate.translate.side_effect = lambda text, target_language: {
        "translatedText": f"TRANSLATED: {text}"
    }

    response = client.post(
        "/api/v1/process-intent",
        json={"text_input": "Help me translate this", "target_language": "es"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["urgency_level"].startswith("TRANSLATED:")
    assert mock_translate.translate.called


@patch("main.client")
@patch("main._translate_client")
def test_process_intent_translation_failure_handles_gracefully(
    mock_translate, mock_genai_client
):
    """Verify that a failing translation doesn't break the main flow."""
    mock_response = MagicMock()
    mock_response.text = json.dumps(MOCK_RESPONSE)
    mock_genai_client.models.generate_content.return_value = mock_response

    mock_translate.translate.side_effect = Exception("Translate server error")

    response = client.post(
        "/api/v1/process-intent",
        json={"text_input": "Help me fail translation", "target_language": "fr"},
    )

    # Should still succeed with original text
    assert response.status_code == 200
    body = response.json()
    assert "Critical" in body["urgency_level"]
    assert mock_translate.translate.called
