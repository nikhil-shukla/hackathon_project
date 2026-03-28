# 🏆 Hackathon Pitch: Aegis AI

## The Hook
*Imagine a woman in distress. She sends a panicked voice note in broken English and uploads a blurry photo of a car accident on a dark road.*
*Within 1.5 seconds, an ambulance is dispatched with a doctor-ready medical summary, and all incoming traffic on Google Maps is re-routed.*
*That’s the power of **Aegis**.*

## 🌍 The Problem
Today, human intent is messy. We communicate in unstructured multi-modal ways—voice, text, and images—but our critical systems (like 911 dispatch, hospital triage, and disaster management) expect rigid, structured data. This gap costs lives, delays emergency response, and creates chaos during crises.

## 💡 Our Solution
**Aegis** acts as an intelligent, universal dispatcher. It's an intent-to-action bridge powered by **Google Gemini AI**.
It transforms messy, multi-modal human inputs directly into verified, structured, actionable workflows.

## 🚀 How It Works
1. **Multi-Modal Ingestion**: The system ingests ambient voice, hasty text, or live camera footage natively using browser APIs and Gemini Multimodal.
2. **AI Reasoning Engine (Gemini 2.5 Pro)**: Gemini doesn't just parse text—it *reasons* over context. It detects the `Critical` urgency level, extracts symptoms, infers possibilities (e.g., myocardial infarction), and formats it into a strict JSON payload.
3. **Action & Execution Layer**: Aegis instantly interfaces with real-world infrastructure:
   - **Google Maps API**: To find the nearest active hospital and automatically launch navigation.
   - **Telephony Webhooks**: To trigger immediate emergency calls.
   - **Data Store**: To create clinical, doctor-ready summaries of the situation before the patient even arrives.

## 🧩 The Tech Stack
* **Intelligence**: Google GenAI SDK (`gemini-2.5-pro`), structured Pydantic mapping.
* **Backend Pipeline**: Python FastAPI—scalable and primed for Google Cloud Run.
* **Frontend Experience**: React + Vite, designed with glassmorphism and extreme accessibility (huge touch targets, high contrast, voice-first triggers) for panicked users.

## 📈 Real-world Applications
1. **Emergency Medical Dispatch**: Overcoming language barriers and panic by instantly generating clinical triage data.
2. **Natural Disaster Coordination**: Processing hundreds of photos and texts from citizens to map real-time flood progression and broadcast evacuation alerts.

## 🏁 The Ask / The Future
With Aegis, we are changing emergency response from **reactive data entry** to **proactive AI dispatching**.
Our next step is directly streaming live body-cam or dashboard-cam footage into Gemini's multi-modal video capabilities to predict crises *before* the first message is even sent.

Thank you!
