from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from google import genai
import os
import json
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Aegis AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# You will need your GEMINI_API_KEY in the environment or .env file
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class Action(BaseModel):
    action_type: str
    parameters: dict

class IntentResponse(BaseModel):
    urgency_level: str
    summary_of_situation: str
    detected_entities: dict
    actions_to_take: List[Action]

class ProcessIntentRequest(BaseModel):
    text_input: Optional[str] = None
    image_base64: Optional[str] = None
    location_data: Optional[Dict[str, float]] = None

SYSTEM_INSTRUCTION = """
You are Aegis, an intelligent dispatcher designed to parse multi-modal input (text, audio transcript, and images) and determine human intent, especially in critical situations. 
Your output MUST strictly conform to the provided JSON schema.

Classify urgency_level into: Low, Medium, High, or Critical.
Extract relevant entities into detected_entities (e.g. location: string, symptoms: array, people: number).
Define actions_to_take where each action has an `action_type` (e.g. 'call_emergency', 'route_maps', 'health_summary', 'disaster_alert', 'general_info') and relevant `parameters` as a dict.
"""

@app.post("/api/v1/process-intent", response_model=IntentResponse)
async def process_intent(req: ProcessIntentRequest):
    if not req.text_input and not req.image_base64:
        raise HTTPException(status_code=400, detail="Must provide text or image input")
    
    prompt = f"User Location: {req.location_data}\n\n" if req.location_data else ""
    if req.text_input:
        prompt += f"Input Text/Transcript: {req.text_input}\n"
    if req.image_base64:
        prompt += "(Image data provided but ignored in simple text call)\n"
        
    try:
        schema_instruction = f"{SYSTEM_INSTRUCTION}\n\nReturn ONLY a valid JSON object strictly matching this schema:\n{json.dumps(IntentResponse.model_json_schema())}"
        response = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt,
            config={
                'system_instruction': schema_instruction,
                'response_mime_type': 'application/json',
            }
        )
        
        parsed_response = json.loads(response.text)
        return parsed_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "healthy"}
