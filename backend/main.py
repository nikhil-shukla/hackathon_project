from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field, field_validator
import base64
from secure import Secure
from typing import List, Optional, Dict, Any
from google import genai
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import json
import time
import hashlib
import logging
import firebase_admin  # type: ignore
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
from google.cloud import bigquery, storage, logging as cloud_logging, translate_v2 as translate  # type: ignore[attr-defined]
from google.api_core.exceptions import GoogleAPICallError

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("aegis")

load_dotenv()

# ── Google Cloud Services init (Firestore, BigQuery, Storage, Logging) ────
_db: Any = None
_bq_client: Any = None
_storage_client: Any = None
_translate_client: Any = None
_gcs_bucket_name = os.getenv("GCS_BUCKET_NAME")

try:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path and os.path.exists(cred_path):
        # 1. Firebase Firestore
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
        logger.info("Firebase Firestore connected ✓")

        # 2. BigQuery
        try:
            _bq_client = bigquery.Client()
            logger.info("Google Cloud BigQuery connected ✓")
        except Exception as bq_exc:
            logger.warning("BigQuery init failed: %s", bq_exc)

        # 3. Cloud Storage
        try:
            _storage_client = storage.Client()
            logger.info("Google Cloud Storage connected ✓")
        except Exception as gcs_exc:
            logger.warning("Cloud Storage init failed: %s", gcs_exc)

        # 4. Cloud Translate
        try:
            _translate_client = translate.Client()
            logger.info("Google Cloud Translate connected ✓")
        except Exception as tr_exc:
            logger.warning("Cloud Translate init failed: %s", tr_exc)

        # 5. Cloud Logging (Native integration)
        try:
            client_logging = cloud_logging.Client()
            client_logging.setup_logging()
            logger.info("Google Cloud Logging integrated ✓")
        except Exception as log_exc:
            logger.warning("Cloud Logging init failed: %s", log_exc)
    else:
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS not set – Cloud data services disabled")
except Exception as exc:
    logger.warning("Google Cloud Services setup failed: %s", exc)


def get_db() -> Any:
    return _db


# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["30/minute"])

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Aegis AI Backend",
    description="Universal Intent-to-Action emergency dispatcher powered by Gemini.",
    version="1.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore

# ── CORS (restrict to known origins) ─────────────────────────────────────────
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,https://aegis-ai.web.app",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── Security Headers ──────────────────────────────────────────────────────────
secure_headers = Secure.with_default_headers()


@app.middleware("http")
async def set_secure_headers(request: Request, call_next):
    response = await call_next(request)
    secure_headers.set_headers(response)
    # Custom Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data:; "
        "connect-src 'self' http://127.0.0.1:8000; "
        "font-src 'self' https://fonts.gstatic.com; "
        "frame-src 'self' https://www.google.com;"
    )
    return response


# ── In-memory response cache ──────────────────────────────────────────────────
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


def _cache_key(text: str, location: Optional[Dict]) -> str:
    raw = f"{text}|{json.dumps(location, sort_keys=True) if location else ''}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[Dict]:
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL_SECONDS:
        logger.info("Cache HIT for key %s", key[:8])
        return entry["data"]
    return None


def _cache_set(key: str, data: Dict) -> None:
    _cache[key] = {"ts": time.time(), "data": data}


# ── Gemini client ─────────────────────────────────────────────────────────────
_gemini_api_key = os.getenv("GEMINI_API_KEY")
if not _gemini_api_key:
    logger.error("GEMINI_API_KEY is not set!")
client = genai.Client(api_key=_gemini_api_key)

# ── Pydantic models ───────────────────────────────────────────────────────────


class Action(BaseModel):
    action_type: str = Field(..., min_length=1, max_length=100)
    parameters: Dict[str, Any] = Field(default_factory=dict)


class IntentResponse(BaseModel):
    urgency_level: str = Field(..., description="Level of urgency (e.g., Low, Medium, High, Critical)")
    summary_of_situation: str
    detected_entities: Dict[str, Any] = Field(default_factory=dict)
    actions_to_take: List[Action] = Field(default_factory=list)


class ProcessIntentRequest(BaseModel):
    text_input: Optional[str] = Field(None, max_length=4000)
    image_base64: Optional[str] = Field(None, max_length=5_000_000)  # ~3.7 MB raw image
    location_data: Optional[Dict[str, float]] = None
    target_language: Optional[str] = Field(None, pattern="^[a-zA-Z]{2}$")  # ISO code like 'es', 'fr'

    @field_validator("text_input")
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            # Basic injection guard
            forbidden = ["<script", "javascript:", "data:text"]
            for token in forbidden:
                if token.lower() in v.lower():
                    raise ValueError("Input contains forbidden content")
        return v


# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_INSTRUCTION = """
You are Aegis, an intelligent emergency dispatcher that parses multi-modal input and
determines human intent – especially in life-critical situations.

Rules:
1. urgency_level MUST be exactly one of: Low | Medium | High | Critical
2. detected_entities is a flat dict with keys like location, symptoms, people_count, etc.
3. actions_to_take is a list where each action has action_type and parameters.
   Valid action_type values: call_emergency | route_maps | health_summary |
   disaster_alert | general_info
4. Return ONLY a valid JSON object – no markdown, no explanation.
"""


# ── Data logging helper (Firestore & BigQuery) ───────────────────────────────
async def _log_data(
    db: Any,
    bq_client: Any,
    request_payload: Dict,
    response_payload: Dict,
    latency_ms: float,
) -> None:
    # Firestore
    if db is not None:
        try:
            doc = {
                "request": request_payload,
                "response": response_payload,
                "latency_ms": latency_ms,
                "timestamp": firestore.SERVER_TIMESTAMP,
            }
            db.collection("aegis_logs").add(doc)
            logger.info("Logged intent to Firestore (%.0f ms latency)", latency_ms)
        except Exception as exc:
            logger.warning("Firestore logging failed: %s", exc)

    # BigQuery structure
    if bq_client is not None:
        try:
            # We assume a dataset 'aegis_ai' and table 'inference_logs' exists.
            # In a real setup, we would ensure this table exists or use insert_rows_json
            table_id = f"{bq_client.project}.aegis_ai.inference_logs"
            rows_to_insert = [
                {
                    "request_text": (
                        request_payload.get("text", "")[:1000]
                        if request_payload.get("text")
                        else None
                    ),
                    "has_image": request_payload.get("has_image", False),
                    "urgency_level": response_payload.get("urgency_level", "Unknown"),
                    "latency_ms": latency_ms,
                    "timestamp": time.time(),
                }
            ]
            # Fire-and-forget for this tutorial-level app (could also log to a file for Fluentd)
            errors = bq_client.insert_rows_json(table_id, rows_to_insert)
            if not errors:
                logger.info("Logged intent metrics to BigQuery ✓")
            else:
                logger.warning("BigQuery insertion errors: %s", errors)
        except GoogleAPICallError as api_exc:
            logger.warning(
                "BigQuery API call failed (Table might not exist): %s", api_exc
            )
        except Exception as exc:
            logger.warning("BigQuery logging failed: %s", exc)

    # BigQuery structure refined for Cloud Trace/Logging context if needed here


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.post(
    "/api/v1/process-intent",
    response_model=IntentResponse,
    summary="Process multi-modal intent",
    tags=["Intent"],
)
@limiter.limit("20/minute")
async def process_intent(
    request: Request,
    req: ProcessIntentRequest,
    db: Any = Depends(get_db),
) -> IntentResponse:
    """
    Analyze text/image input and return a structured emergency-action plan.

    - **text_input**: Plain-text description of the situation
    - **image_base64**: Base64-encoded image (optional)
    - **location_data**: `{"lat": float, "lng": float}` (optional)
    """
    if not req.text_input and not req.image_base64:
        raise HTTPException(
            status_code=400, detail="Must provide text_input or image_base64"
        )

    # Build prompt and contents for Gemini
    # Gemini 2.x supports list of parts: strings and bytes (for images)
    prompt_parts: List[Any] = []

    # Contextual string prompt
    text_prompt = ""
    if req.location_data:
        text_prompt += f"User Location (lat/lng): {req.location_data}\n"
    if req.text_input:
        text_prompt += f"Situation Description: {req.text_input}\n"

    prompt_parts.append(text_prompt)

    # Attach image if provided
    if req.image_base64:
        try:
            # Handle possible prefix like 'data:image/png;base64,' if they sent it
            if "," in req.image_base64:
                b64_data = req.image_base64.split(",")[1]
            else:
                b64_data = req.image_base64

            img_bytes = base64.b64decode(b64_data)
            
            # ── [NEW] Google Cloud Storage Integration ─────────────────────
            # Save incident image to GCS if bucket is configured
            if _storage_client and _gcs_bucket_name:
                try:
                    bucket = _storage_client.bucket(_gcs_bucket_name)
                    blob_name = f"incidents/{int(time.time())}_{hashlib.md5(img_bytes).hexdigest()[:8]}.jpg"
                    blob = bucket.blob(blob_name)
                    blob.upload_from_string(img_bytes, content_type="image/jpeg")
                    logger.info("Incident image persisted to GCS: %s", blob_name)
                except Exception as gcs_err:
                    logger.warning("Failed to persist to GCS: %s", gcs_err)

            # Using genai parts schema
            prompt_parts.append(
                genai.types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg")
            )
            logger.info("Image data attached to Gemini request")
        except Exception as e:
            logger.error("Failed to decode image: %s", e)
            raise HTTPException(status_code=400, detail="Invalid image encoding")

    # Cache check (on text part mostly as hashing binary is expensive but possible)
    cache_key = _cache_key(text_prompt, req.location_data)
    cached = _cache_get(cache_key)
    if (
        cached is not None and not req.image_base64
    ):  # Don't cache image results if you want fresh vision context
        return IntentResponse(**cached)

    schema_instruction = (
        f"{SYSTEM_INSTRUCTION}\n\n"
        f"Return ONLY a valid JSON object strictly matching this schema:\n"
        f"{json.dumps(IntentResponse.model_json_schema(), indent=2)}"
    )

    t0 = time.perf_counter()
    try:
        # Multimodal call
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt_parts,
            config={
                "system_instruction": schema_instruction,
                "response_mime_type": "application/json",
            },
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        logger.info("Gemini responded in %.0f ms", latency_ms)
    except Exception as exc:
        logger.exception("Gemini API error")
        raise HTTPException(status_code=502, detail=f"AI service error: {str(exc)}")

    try:
        response_text = str(response.text) if response.text else ""
        parsed: Dict = json.loads(response_text)
        validated = IntentResponse(**parsed)
    except (json.JSONDecodeError, Exception) as exc:
        logger.error(
            "Response validation failed: %s | raw: %s", exc, str(response.text)[:200] if response.text else "None"
        )
        raise HTTPException(
            status_code=500, detail="Invalid response format from AI model"
        )

    result_dict = validated.model_dump()
    _cache_set(cache_key, result_dict)

    # ── [NEW] Google Cloud Translate Integration ────────────────────
    # If a target language is requested, translate the key fields
    if req.target_language and _translate_client:
        try:
            lang = req.target_language
            fields_to_translate = ["urgency_level", "summary_of_situation"]
            
            # Map original names to translated names for easy replacement
            for field in fields_to_translate:
                res = _translate_client.translate(result_dict[field], target_language=lang)
                result_dict[field] = res["translatedText"]
                
            # Optionally translate actions (deep mapping)
            for action in result_dict.get("actions_to_take", []):
                # Translate action type or descriptions if they existed (not in this schema yet)
                pass
                
            logger.info("Results translated to %s", lang)
        except Exception as tr_err:
            logger.warning("Translation failed: %s", tr_err)

    # Log to Data Stores asynchronously (best-effort)
    await _log_data(
        db,
        _bq_client,
        request_payload={"text": req.text_input, "has_image": bool(req.image_base64)},
        response_payload=result_dict,
        latency_ms=latency_ms,
    )

    return IntentResponse(**result_dict)


@app.get("/health", summary="Health check", tags=["System"])
async def health_check() -> Dict[str, str]:
    """Returns service health status."""
    return {
        "status": "healthy",
        "version": "1.2.0",
        "firebase": "connected" if _db else "disabled",
    }


@app.get("/api/v1/cache/stats", summary="Cache statistics", tags=["System"])
async def cache_stats() -> Dict[str, Any]:
    """Returns in-memory cache size and TTL."""
    return {
        "cached_entries": len(_cache),
        "ttl_seconds": CACHE_TTL_SECONDS,
    }
