import { useState, useRef, useEffect } from 'react';
import './App.css';
import { Mic, Image as ImageIcon, Send, Loader2, AlertTriangle, MapPin, Activity, Phone, Info } from 'lucide-react';

interface Action {
  action_type: string;
  parameters: Record<string, any>;
}

interface IntentResponse {
  urgency_level: string;
  summary_of_situation: string;
  detected_entities: Record<string, any>;
  actions_to_take: Action[];
}

function App() {
  const [textInput, setTextInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState<IntentResponse | null>(null);
  const [location, setLocation] = useState<{lat: number, lng: number} | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api/v1/process-intent';

  useEffect(() => {
    // Attempt to get user location
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => setLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        (err) => console.log('Location access denied', err)
      );
    }
  }, []);

  const handleSubmit = async () => {
    if (!textInput.trim()) return;
    setIsLoading(true);
    setResponse(null);
    
    try {
      const res = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text_input: textInput,
          location_data: location
        })
      });
      
      if (!res.ok) throw new Error('API Error');
      
      const data: IntentResponse = await res.json();
      setResponse(data);
    } catch (err) {
      console.error(err);
      alert('Failed to process intent. Please check if backend is running.');
    } finally {
      setIsLoading(false);
    }
  };

  const getUrgencyClass = (urgency: string) => {
    switch (urgency.toLowerCase()) {
      case 'critical': return 'urgency-critical';
      case 'high': return 'urgency-high';
      case 'medium': return 'urgency-medium';
      case 'low': return 'urgency-low';
      default: return 'urgency-low';
    }
  };

  const renderActionIcon = (type: string) => {
    switch (type.toLowerCase()) {
      case 'call_emergency': return <Phone size={24} color="#ff4b4b" />;
      case 'route_maps': return <MapPin size={24} color="#fca311" />;
      case 'health_summary': return <Activity size={24} color="#2ecc71" />;
      default: return <Info size={24} color="#3498db" />;
    }
  };
  
  // Simulated Voice Recording
  const handleRecord = () => {
    if (isRecording) {
      setIsRecording(false);
    } else {
      setIsRecording(true);
      setTextInput("");
      
      // Simulate real-time transcription since browser SpeechRecognition can be finicky
      setTimeout(() => setTextInput("My father is sweating, chest pain, we are near a crowded road and traffic is bad..."), 1500);
      setTimeout(() => setIsRecording(false), 3000);
    }
  };

  return (
    <div className="app-container">
      <header>
        <h1 className="title">Aegis AI</h1>
        <p className="subtitle">Universal Intent-to-Action Bridge</p>
      </header>

      <div className="main-interface glass animate-in">
        <div className="input-section">
          <div className="controls-row">
            <button 
              className={`btn btn-icon-large ${isRecording ? 'btn-danger pulse-recording' : 'glass'}`} 
              onClick={handleRecord}
              title="Hold to Speak"
            >
              <Mic size={32} color={isRecording ? "#fff" : "var(--accent-glow)"} />
            </button>
            
            <button 
              className="btn glass btn-icon-large" 
              onClick={() => fileInputRef.current?.click()}
              title="Upload Image"
            >
              <ImageIcon size={32} color="var(--accent-glow)" />
            </button>
            <input type="file" ref={fileInputRef} className="hidden-input" accept="image/*" />
          </div>

          <div className="text-input-wrapper">
            <textarea 
              placeholder="Describe the situation, upload an image, or speak directly..."
              value={textInput}
              onChange={(e) => setTextInput(e.target.value)}
            />
            <div className="action-bar">
              <button 
                className="btn btn-primary" 
                onClick={handleSubmit} 
                disabled={isLoading || !textInput.trim()}
              >
                {isLoading ? <Loader2 className="animate-spin" size={20} /> : <Send size={20} />}
                Process Intent
              </button>
            </div>
          </div>
        </div>
      </div>

      {response && (
        <div className="main-interface glass animate-in results-section">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2><AlertTriangle size={24} style={{ display: 'inline', marginRight: '10px', verticalAlign: 'middle' }} /> Analysis Complete</h2>
            <span className={`urgency-badge ${getUrgencyClass(response.urgency_level)}`}>
              {response.urgency_level}
            </span>
          </div>
          
          <div className="summary-box">
            <p className="subtitle" style={{ color: '#fff' }}>{response.summary_of_situation}</p>
          </div>
          
          {Object.keys(response.detected_entities).length > 0 && (
            <div>
              <h3 style={{ fontSize: '1rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>Detected Entities</h3>
              <div className="entities-grid">
                {Object.entries(response.detected_entities).map(([key, value], idx) => (
                  <span key={idx} className="entity-tag">
                    {key}: {Array.isArray(value) ? value.join(', ') : String(value)}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div>
            <h3 style={{ fontSize: '1.2rem', marginTop: '10px', color: 'var(--accent-glow)' }}>Recommended Actions</h3>
            <div className="actions-list">
              {response.actions_to_take.map((action, idx) => (
                <div key={idx} className="action-card">
                  <div className="action-title">
                    {renderActionIcon(action.action_type)}
                    {action.action_type.replace(/_/g, ' ').toUpperCase()}
                  </div>
                  <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                    {Object.entries(action.parameters).map(([key, val], pIdx) => (
                      <div key={pIdx}><strong>{key}:</strong> {String(val)}</div>
                    ))}
                  </div>
                  {action.action_type === 'call_emergency' && (
                    <button className="btn btn-danger" style={{ marginTop: '10px' }} onClick={() => window.open('tel:911')}>
                      Call 911 Now
                    </button>
                  )}
                  {action.action_type === 'route_maps' && (
                    <button className="btn btn-primary" style={{ marginTop: '10px' }} onClick={() => window.open(`https://www.google.com/maps/dir/?api=1&destination=${action.parameters.destination || 'Nearest Hospital'}`)}>
                      Open Maps
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
