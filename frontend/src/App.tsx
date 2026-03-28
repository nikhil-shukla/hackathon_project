import { useState, useRef, useEffect, useCallback } from 'react';
import './App.css';
import { Mic, Image as ImageIcon, Send, Loader2, AlertTriangle, MapPin, Activity, Phone, Info, ShieldCheck, X } from 'lucide-react';

interface Action {
  action_type: string;
  parameters: Record<string, unknown>;
}

interface IntentResponse {
  urgency_level: string;
  summary_of_situation: string;
  detected_entities: Record<string, unknown>;
  actions_to_take: Action[];
}

// ------------------------------------------------------------------
// Web Speech API types (not in standard lib – declare manually)
// ------------------------------------------------------------------
interface ISpeechRecognitionResult {
  readonly 0: { readonly transcript: string };
  readonly length: number;
}
interface ISpeechRecognitionResultList {
  readonly 0: ISpeechRecognitionResult;
  readonly length: number;
}
interface ISpeechRecognitionEvent extends Event {
  results: ISpeechRecognitionResultList;
}
interface ISpeechRecognition extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: ISpeechRecognitionEvent) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}
interface ISpeechRecognitionConstructor {
  new(): ISpeechRecognition;
}

type ExtendedWindow = Window & {
  SpeechRecognition?: ISpeechRecognitionConstructor;
  webkitSpeechRecognition?: ISpeechRecognitionConstructor;
};

const SpeechRecognitionAPI: ISpeechRecognitionConstructor | undefined =
  typeof window !== 'undefined'
    ? ((window as ExtendedWindow).SpeechRecognition ||
       (window as ExtendedWindow).webkitSpeechRecognition)
    : undefined;

function App() {
  const [textInput, setTextInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState<IntentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [location, setLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string>('');   // for screen readers

  const fileInputRef = useRef<HTMLInputElement>(null);
  const recognitionRef = useRef<ISpeechRecognition | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1/process-intent';

  // Geolocation
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude });
          setStatusMsg('Location acquired.');
        },
        () => setStatusMsg('Location access denied – continuing without it.')
      );
    }
  }, []);

  // Auto-scroll to results
  useEffect(() => {
    if (response && resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' });
      resultsRef.current.focus();
    }
  }, [response]);

  // ── Voice recording ────────────────────────────────────────────────────────
  const handleRecord = useCallback(() => {
    if (isRecording) {
      recognitionRef.current?.stop();
      setIsRecording(false);
      return;
    }

    if (SpeechRecognitionAPI) {
      const recognition = new SpeechRecognitionAPI();
      recognition.lang = 'en-US';
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.onresult = (e: ISpeechRecognitionEvent) => {
        const transcript = e.results[0][0].transcript;
        setTextInput((prev) => (prev ? prev + ' ' + transcript : transcript));
        setStatusMsg(`Transcribed: ${transcript}`);
      };
      recognition.onerror = () => setStatusMsg('Voice recognition error. Please type instead.');
      recognition.onend = () => setIsRecording(false);
      recognitionRef.current = recognition;
      recognition.start();
    } else {
      // Graceful sim fallback
      setTextInput('My father is sweating, chest pain, we are near a crowded road and traffic is bad...');
      setTimeout(() => setIsRecording(false), 2500);
    }
    setIsRecording(true);
    setStatusMsg('Listening… speak now.');
  }, [isRecording]);

  // ── Image upload ───────────────────────────────────────────────────────────
  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 4_000_000) {
      setError('Image must be smaller than 4 MB.');
      return;
    }
    const reader = new FileReader();
    reader.onloadend = () => {
      const b64 = (reader.result as string).split(',')[1];
      setImageBase64(b64);
      setImagePreview(reader.result as string);
      setStatusMsg('Image attached successfully.');
    };
    reader.readAsDataURL(file);
  };

  const removeImage = () => {
    setImageBase64(null);
    setImagePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setStatusMsg('Image removed.');
  };

  // ── Submit ─────────────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    if (!textInput.trim() && !imageBase64) return;
    setIsLoading(true);
    setResponse(null);
    setError(null);
    setStatusMsg('Analyzing situation…');

    try {
      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text_input: textInput || undefined,
          image_base64: imageBase64 || undefined,
          location_data: location,
        }),
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(errBody.detail || `HTTP ${res.status}`);
      }

      const data: IntentResponse = await res.json();
      setResponse(data);
      setStatusMsg(`Analysis complete. Urgency: ${data.urgency_level}.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setError(`Failed to process intent: ${msg}`);
      setStatusMsg('Error processing request.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') handleSubmit();
  };

  // ── Helpers ────────────────────────────────────────────────────────────────
  const getUrgencyClass = (urgency: string) => {
    switch (urgency.toLowerCase()) {
      case 'critical': return 'urgency-critical';
      case 'high':     return 'urgency-high';
      case 'medium':   return 'urgency-medium';
      default:         return 'urgency-low';
    }
  };

  const renderActionIcon = (type: string) => {
    const props = { size: 22, 'aria-hidden': true };
    switch (type.toLowerCase()) {
      case 'call_emergency': return <Phone {...props} color="#ff4b4b" />;
      case 'route_maps':     return <MapPin {...props} color="#fca311" />;
      case 'health_summary': return <Activity {...props} color="#2ecc71" />;
      case 'disaster_alert': return <AlertTriangle {...props} color="#ff6b35" />;
      default:               return <Info {...props} color="#3498db" />;
    }
  };

  const buildMapsUrl = (action: Action) => {
    const dest = encodeURIComponent((action.parameters.destination as string) || 'Nearest Hospital');
    const origin = location
      ? `&origin=${location.lat},${location.lng}`
      : '';
    return `https://www.google.com/maps/dir/?api=1&destination=${dest}${origin}&travelmode=driving`;
  };

  const buildEmbedMapsUrl = () => {
    if (!location) return null;
    const key = import.meta.env.VITE_MAPS_API_KEY || '';
    if (!key) return null;
    return `https://www.google.com/maps/embed/v1/view?key=${key}&center=${location.lat},${location.lng}&zoom=14`;
  };

  const embedMapsUrl = buildEmbedMapsUrl();

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="app-container">
      {/* Accessible live region for screen reader announcements */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {statusMsg}
      </div>

      {/* Skip to main content */}
      <a href="#main-input" className="skip-link">Skip to main content</a>

      <header role="banner">
        <div className="logo-row" aria-hidden="true">
          <ShieldCheck size={40} color="var(--accent-glow)" strokeWidth={1.5} />
        </div>
        <h1 className="title">Aegis AI</h1>
        <p className="subtitle" id="app-description">
          Universal Intent-to-Action Emergency Bridge · Powered by Gemini
        </p>
        {location && (
          <p className="location-pill" aria-label={`Location detected: ${location.lat.toFixed(4)}, ${location.lng.toFixed(4)}`}>
            <MapPin size={14} aria-hidden="true" /> {location.lat.toFixed(4)}, {location.lng.toFixed(4)}
          </p>
        )}
      </header>

      <main
        id="main-input"
        className="main-interface glass animate-in"
        role="main"
        aria-labelledby="input-heading"
      >
        <section className="input-section" aria-label="Situation input">
          <h2 id="input-heading" className="sr-only">Describe the Situation</h2>

          {/* Control buttons */}
          <div className="controls-row" role="group" aria-label="Input methods">
            <button
              id="btn-voice"
              className={`btn btn-icon-large ${isRecording ? 'btn-danger pulse-recording' : 'glass'}`}
              onClick={handleRecord}
              aria-label={isRecording ? 'Stop recording' : 'Start voice recording'}
              aria-pressed={isRecording}
              title={isRecording ? 'Stop recording' : 'Tap to speak'}
            >
              <Mic size={32} color={isRecording ? '#fff' : 'var(--accent-glow)'} aria-hidden="true" />
            </button>

            <button
              id="btn-image"
              className="btn glass btn-icon-large"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Upload an image of the situation"
              title="Attach an image"
            >
              <ImageIcon size={32} color="var(--accent-glow)" aria-hidden="true" />
            </button>

            <input
              ref={fileInputRef}
              type="file"
              id="file-input"
              className="hidden-input"
              accept="image/*"
              aria-label="Image file input"
              onChange={handleImageChange}
            />
          </div>

          {/* Image preview */}
          {imagePreview && (
            <div className="image-preview-wrapper" role="group" aria-label="Attached image">
              <img
                src={imagePreview}
                alt="Uploaded situation preview"
                className="photo-preview"
              />
              <button
                className="btn btn-icon-small remove-img"
                onClick={removeImage}
                aria-label="Remove attached image"
                title="Remove image"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>
          )}

          {/* Text area */}
          <div className="text-input-wrapper">
            <label htmlFor="situation-input" className="sr-only">
              Describe the situation (or use voice / image above)
            </label>
            <textarea
              id="situation-input"
              ref={textareaRef}
              placeholder="Describe the situation, upload an image, or use voice input…"
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
              onKeyDown={handleKeyDown}
              aria-describedby="app-description textarea-hint"
              aria-label="Situation description"
              aria-required="true"
              minLength={1}
              maxLength={4000}
            />
            <p id="textarea-hint" className="input-hint" aria-live="off">
              Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> to submit · {4000 - textInput.length} characters remaining
            </p>

            <div className="action-bar">
              <button
                id="btn-submit"
                className="btn btn-primary"
                onClick={handleSubmit}
                disabled={isLoading || (!textInput.trim() && !imageBase64)}
                aria-label={isLoading ? 'Processing, please wait' : 'Process intent and get action plan'}
                aria-busy={isLoading}
              >
                {isLoading
                  ? <><Loader2 className="animate-spin" size={20} aria-hidden="true" /> Analyzing…</>
                  : <><Send size={20} aria-hidden="true" /> Process Intent</>
                }
              </button>
            </div>
          </div>
        </section>
      </main>

      {/* Error banner */}
      {error && (
        <div
          role="alert"
          aria-live="assertive"
          className="error-banner"
        >
          <AlertTriangle size={20} aria-hidden="true" />
          {error}
          <button className="btn btn-icon-small" onClick={() => setError(null)} aria-label="Dismiss error">
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      )}

      {/* ── Results ──────────────────────────────────────────────────────── */}
      {response && (
        <section
          ref={resultsRef}
          tabIndex={-1}
          className="main-interface glass animate-in results-section"
          aria-label="Analysis results"
          aria-live="polite"
        >
          {/* Header */}
          <div className="results-header">
            <h2 id="results-heading">
              <AlertTriangle size={22} style={{ display: 'inline', marginRight: 8, verticalAlign: 'middle' }} aria-hidden="true" />
              Analysis Complete
            </h2>
            <span
              className={`urgency-badge ${getUrgencyClass(response.urgency_level)}`}
              aria-label={`Urgency level: ${response.urgency_level}`}
              role="status"
            >
              {response.urgency_level}
            </span>
          </div>

          {/* Summary */}
          <div className="summary-box" aria-label="Situation summary">
            <p className="subtitle" style={{ color: '#fff' }}>{response.summary_of_situation}</p>
          </div>

          {/* Detected entities */}
          {Object.keys(response.detected_entities).length > 0 && (
            <div aria-labelledby="entities-heading">
              <h3 id="entities-heading" style={{ fontSize: '1rem', color: 'var(--text-secondary)', marginBottom: 8 }}>
                Detected Entities
              </h3>
              <ul className="entities-grid" aria-label="Detected entities list">
                {Object.entries(response.detected_entities).map(([key, value], idx) => (
                  <li key={idx} className="entity-tag">
                    <strong>{key}:</strong>{' '}
                    {Array.isArray(value) ? value.join(', ') : String(value)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Google Maps embed (if location + API key available) */}
          {embedMapsUrl && (
            <div className="maps-embed-wrapper" aria-label="Your current location on Google Maps">
              <h3 style={{ fontSize: '1rem', color: 'var(--text-secondary)', marginBottom: 8 }}>
                <MapPin size={16} aria-hidden="true" /> Your Location
              </h3>
              <iframe
                title="Google Maps – current location"
                src={embedMapsUrl}
                width="100%"
                height="220"
                style={{ border: 0, borderRadius: 12 }}
                allowFullScreen
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
                aria-label="Google Maps showing your current location"
              />
            </div>
          )}

          {/* Recommended actions */}
          <div aria-labelledby="actions-heading">
            <h3 id="actions-heading" style={{ fontSize: '1.2rem', marginTop: 10, color: 'var(--accent-glow)' }}>
              Recommended Actions
            </h3>
            <ul className="actions-list" aria-label="List of recommended actions">
              {response.actions_to_take.map((action, idx) => (
                <li key={idx} className="action-card" aria-label={`Action: ${action.action_type.replace(/_/g, ' ')}`}>
                  <div className="action-title" aria-hidden="false">
                    {renderActionIcon(action.action_type)}
                    <span>{action.action_type.replace(/_/g, ' ').toUpperCase()}</span>
                  </div>
                  <dl style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                    {Object.entries(action.parameters).map(([key, val], pIdx) => (
                      <div key={pIdx} className="param-row">
                        <dt><strong>{key}:</strong></dt>
                        <dd>{String(val)}</dd>
                      </div>
                    ))}
                  </dl>

                  {action.action_type === 'call_emergency' && (
                    <a
                      href="tel:911"
                      className="btn btn-danger"
                      style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}
                      aria-label="Call emergency services (911)"
                    >
                      <Phone size={16} aria-hidden="true" /> Call 911 Now
                    </a>
                  )}

                  {action.action_type === 'route_maps' && (
                    <a
                      href={buildMapsUrl(action)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-primary"
                      style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 6 }}
                      aria-label={`Open Google Maps directions to ${action.parameters.destination || 'nearest hospital'} (opens in new tab)`}
                    >
                      <MapPin size={16} aria-hidden="true" /> Open Google Maps
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </div>
  );
}

export default App;
