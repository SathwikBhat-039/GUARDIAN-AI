import React, { useState, useEffect } from 'react';
import {
  Shield,
  Video,
  MapPin,
  AlertTriangle,
  Bell,
  History,
  Plus,
  Play,
  Navigation,
  Hospital,
  ShieldAlert,
  Flame,
  Globe,
  Settings,
  User
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');

const App = () => {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [events, setEvents] = useState([]);
  const [videoLink, setVideoLink] = useState('');
  const [selectedEvent, setSelectedEvent] = useState(null);
  const [locationInfo, setLocationInfo] = useState(null);
  const [isLive, setIsLive] = useState(false);
  const [livePrediction, setLivePrediction] = useState(null);
  const [linkResult, setLinkResult] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [systemStats, setSystemStats] = useState({ cpu: 24, mem: 42, gpu: 18 });

  const videoRef = React.useRef(null);
  const canvasRef = React.useRef(null);
  const socketRef = React.useRef(null);
  const isLiveRef = React.useRef(false);

  useEffect(() => {
    // Inject custom scrollbar and mission control styles
    const styleSheet = document.createElement("style");
    styleSheet.innerText = `
      .custom-scrollbar::-webkit-scrollbar { width: 6px; }
      .custom-scrollbar::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.1); }
      .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(16, 185, 129, 0.3); border-radius: 10px; }
      .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(16, 185, 129, 0.5); }
      .analysis-info-box {
        background: rgba(16, 185, 129, 0.05);
        backdrop-filter: blur(20px);
        border: 1px solid rgba(16, 185, 129, 0.2);
        transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
      }
      .analysis-info-box:hover {
        border-color: rgba(16, 185, 129, 0.4);
        box-shadow: 0 0 30px rgba(16, 185, 129, 0.1);
      }
      .info-stat-premium {
        background: rgba(255, 255, 255, 0.03);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 1.5rem;
        padding: 1.5rem;
        transition: all 0.3s ease;
      }
      .info-stat-premium:hover {
        background: rgba(255, 255, 255, 0.05);
        transform: translateY(-5px);
        border-color: rgba(16, 185, 129, 0.3);
      }
    `;
    document.head.appendChild(styleSheet);

    fetchEvents();
    fetchLocation();
    const interval = setInterval(fetchEvents, 10000);

    const statsInterval = setInterval(() => {
      setSystemStats({
        cpu: Math.floor(20 + Math.random() * 15),
        mem: Math.floor(35 + Math.random() * 10),
        gpu: Math.floor(15 + Math.random() * 25)
      });
    }, 3000);

    return () => {
      clearInterval(interval);
      clearInterval(statsInterval);
    };
  }, []);

  const startLive = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, frameRate: 15 }
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        setIsLive(true);
        isLiveRef.current = true;

        const connectWebSocket = () => {
          socketRef.current = new WebSocket(`${WS_BASE_URL}/api/ws/live`);

          socketRef.current.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.status === 'detected' || data.status === 'buffering') {
              setLivePrediction(prev => ({
                ...prev,
                ...data,
                class: data.class || (prev?.class),
                confidence: data.confidence || (prev?.confidence)
              }));
            }
          };

          socketRef.current.onopen = () => {
            console.log("WebSocket connected / Reconnected");
          };
        };

        connectWebSocket();

        const sendFrame = () => {
          if (!isLiveRef.current) return;

          if (!socketRef.current || socketRef.current.readyState === WebSocket.CLOSED) {
            connectWebSocket();
          }

          if (socketRef.current?.readyState === WebSocket.OPEN && canvasRef.current && videoRef.current) {
            const context = canvasRef.current.getContext('2d');
            // Ensure we only draw if the video is ready
            if (videoRef.current.readyState >= 2) {
              context.drawImage(videoRef.current, 0, 0, 640, 480);
              const base64Image = canvasRef.current.toDataURL('image/jpeg', 0.5);
              socketRef.current.send(base64Image);
            }
          }
          // Slow down the request animation frame slightly to avoid saturating the socket
          setTimeout(() => { if (isLiveRef.current) requestAnimationFrame(sendFrame); }, 150);
        };

        sendFrame();
      }
    } catch (err) {
      console.error("Camera access denied", err);
      alert("Please allow camera access to use this feature. Make sure no other app is using the camera.");
    }
  };

  const stopLive = () => {
    isLiveRef.current = false;
    if (videoRef.current?.srcObject) {
      videoRef.current.srcObject.getTracks().forEach(track => track.stop());
      videoRef.current.srcObject = null;
    }
    if (socketRef.current) {
      socketRef.current.close();
    }
    setIsLive(false);
    setLivePrediction(null);
  };

  const fetchEvents = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/events`);
      setEvents(response.data);
      if (response.data.length > 0 && !selectedEvent) {
        setSelectedEvent(response.data[0]);
      }
    } catch (error) {
      console.error("Failed to fetch events", error);
    }
  };

  const fetchLocation = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/location`);
      setLocationInfo(response.data);
    } catch (error) {
      console.error("Failed to fetch location", error);
    }
  };

  const handleLinkSubmit = async (e) => {
    e.preventDefault();
    if (!videoLink) return;

    setErrorMessage(null);
    setLinkResult({ status: 'processing', prediction: 'Analyzing...', confidence: 0 });
    setIsProcessing(true);

    try {
      const res = await axios.post(`${API_BASE_URL}/api/process_link`, { url: videoLink });
      const data = res.data;

      // Update result immediately with classification data
      setLinkResult({ ...data, status: 'success' });

      if (data.status === 'success') {
        const taskId = data.task_id;

        // Polling for video completion
        const checkStatus = async () => {
          try {
            const statusRes = await axios.get(`${API_BASE_URL}/api/video_status/${taskId}`);
            if (statusRes.data.status === 'ready') {
              setIsProcessing(false);
              const newEvent = {
                id: taskId,
                type: data.prediction,
                url: statusRes.data.url,
                timestamp: new Date().toLocaleTimeString(),
                location: data.location || locationInfo?.address,
                device: 'Manual AI Analysis'
              };
              setSelectedEvent(newEvent);
              fetchEvents();
            } else if (statusRes.data.status === 'error') {
              setIsProcessing(false);
              setErrorMessage("AI rendering failed for this clip.");
            } else {
              setTimeout(checkStatus, 2000);
            }
          } catch (e) {
            console.error("Status check failed", e);
          }
        };

        checkStatus();

        if (data.location && data.nearby_facilities) {
          setLocationInfo({
            address: data.location,
            nearby: data.nearby_facilities
          });
        }
      }
      setVideoLink('');
    } catch (error) {
      setIsProcessing(false);
      setLinkResult(null);
      const msg = error.response?.data?.detail || "Connection Error: Check if server is running";
      setErrorMessage(msg);
      setTimeout(() => setErrorMessage(null), 5000);
    }
  };

  return (
    <div className="app-container">
      <canvas ref={canvasRef} width="640" height="480" style={{ display: 'none' }} />
      {/* Sidebar */}
      <nav className="sidebar glass-morphism">
        <div className="logo-container">
          <Shield className="logo-icon" size={32} />
          <span className="logo-text">AVTAR</span>
          <span className="logo-subtext">SMART SECURITY</span>
        </div>

        <div className="nav-links">
          <button
            className={`nav-item ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => { setActiveTab('dashboard'); stopLive(); }}
          >
            <div className="nav-icon-box"><Globe size={18} /></div>
            <span>Global View</span>
          </button>
          <button
            className={`nav-item ${activeTab === 'cameras' ? 'active' : ''}`}
            onClick={() => setActiveTab('cameras')}
          >
            <div className="nav-icon-box"><Video size={18} /></div>
            <span>Surveillance Grid</span>
          </button>
          <button
            className={`nav-item ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => { setActiveTab('history'); stopLive(); }}
          >
            <div className="nav-icon-box"><History size={18} /></div>
            <span>Intelligence Logs</span>
          </button>
          <button
            className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab('settings')}
          >
            <div className="nav-icon-box"><Settings size={18} /></div>
            <span>System Config</span>
          </button>
        </div>

        <div className="user-profile">
          <div className="avatar glass-morphism">
            <User size={20} />
          </div>
          <div className="user-info">
            <p className="user-name">Admin User</p>
            <p className="user-status">Verified Agent</p>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="main-content">
        <header className="top-header glass-morphism">
          <div className="search-bar">
            {isProcessing ? (
              <div className="animate-spin h-4 w-4 border-2 border-emerald-500 border-t-transparent rounded-full" />
            ) : errorMessage ? (
              <AlertTriangle size={18} className="text-red-500 animate-pulse" />
            ) : (
              <Video size={18} className="text-emerald-500" />
            )}
            <form onSubmit={handleLinkSubmit} style={{ flexGrow: 1 }}>
              <input
                type="text"
                placeholder={errorMessage ? `Error: ${errorMessage}` : "Enter a local video path"}
                value={videoLink}
                onChange={(e) => setVideoLink(e.target.value)}
                className={errorMessage ? 'text-red-400 placeholder-red-400/50' : ''}
              />
            </form>
            <button
              type="submit"
              onClick={handleLinkSubmit}
              disabled={isProcessing}
              className={`px-4 py-1 border rounded-lg transition-all text-xs font-black tracking-widest ${isProcessing ? 'bg-gray-800 text-gray-500 border-gray-700' : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 hover:bg-emerald-500/20'}`}
            >
              {isProcessing ? 'RUNNING' : 'INFERENCE'}
            </button>
          </div>

          <div className="system-metrics">
            <div className="metric">
              <span className="label">CPU</span>
              <span className="value">{systemStats.cpu}%</span>
            </div>
            <div className="metric">
              <span className="label">MEM</span>
              <span className="value">{systemStats.mem}%</span>
            </div>
            <div className="metric">
              <span className="label">GPU</span>
              <span className="value">{systemStats.gpu}%</span>
            </div>
          </div>

          <div className="header-actions">
            <div className="header-icon-btn glass-morphism">
              <Bell size={18} />
              <span className="badge"></span>
            </div>
          </div>
        </header>

        <div className="dashboard-grid">
          {/* Main Video Section */}
          <section className="live-feed-section glass-morphism">
            <div className="section-header">
              <div className="flex items-center gap-2">
                <div className="live-indicator"></div>
                <h3>{activeTab === 'cameras' ? 'Hardware Camera' : 'Active Surveillance'}</h3>
              </div>
              <div className="flex gap-2">
                {activeTab === 'cameras' && (
                  !isLive ?
                    <button onClick={startLive} className="live-btn start"><Play size={14} /> Start Camera</button> :
                    <button onClick={stopLive} className="live-btn stop">Stop Camera</button>
                )}
                <span className="text-muted text-sm">{activeTab === 'cameras' ? 'Local Video' : (selectedEvent?.device || 'Scanning Cameras...')}</span>
              </div>
            </div>

            <div className="video-player-container glass-morphism">
              <div className="scan-line"></div>
              {activeTab === 'cameras' ? (
                <div className="webcam-view relative w-full h-full bg-black overflow-hidden flex items-center justify-center">
                  <video
                    ref={videoRef}
                    autoPlay
                    playsInline
                    muted
                    className="main-video w-full h-full object-contain"
                    style={{ position: 'relative', zIndex: 1, filter: 'contrast(1.1) brightness(1.1)' }}
                  />
                  {livePrediction?.image && (
                    <img
                      src={`data:image/jpeg;base64,${livePrediction.image}`}
                      className="YOLO-stream absolute inset-0 w-full h-full object-contain"
                      alt="YOLO overlay"
                      style={{ zIndex: 10, pointerEvents: 'none' }}
                    />
                  )}
                  <div className="camera-id-tag">CAM-SEC-081 // LIVE</div>
                  {isLive && (
                    <div className="live-ai-overlay" style={{ zIndex: 20 }}>
                      <div className="flex items-center gap-2 mb-2">
                        <div className="pulse-red"></div>
                        <p className="text-[10px] font-bold tracking-[0.2em] text-white/50">NEURAL PROCESSOR ACTIVE</p>
                      </div>
                      <div className="prediction-box">
                        {livePrediction?.class ? (
                          <div className="flex flex-col">
                            <span className={`text-xl font-black tracking-tighter uppercase ${livePrediction.class.toLowerCase() === 'normal' ? 'text-emerald-400' : 'text-red-500'}`}>{livePrediction.class}</span>
                            <div className="flex items-center gap-2 mt-1">
                              <div className="h-1 w-20 bg-white/10 rounded-full overflow-hidden">
                                <motion.div
                                  initial={{ width: 0 }}
                                  animate={{ width: `${Math.round((livePrediction.confidence || 0) * 100)}%` }}
                                  className={`h-full ${livePrediction.class.toLowerCase() === 'normal' ? 'bg-emerald-500' : 'bg-red-500'}`}
                                />
                              </div>
                              <span className="text-[10px] font-mono text-white/70">{Math.round((livePrediction.confidence || 0) * 100)}%</span>
                            </div>
                            {livePrediction.class.toLowerCase() !== 'normal' && (
                              <motion.div
                                animate={{ opacity: [1, 0.5, 1] }}
                                transition={{ repeat: Infinity, duration: 1 }}
                                className="alert-badge-mini mt-2"
                              >
                                <AlertTriangle size={10} /> PROTOCOL ALPHA INITIATED
                              </motion.div>
                            )}
                          </div>
                        ) : (
                          <div className="flex flex-col gap-2">
                            <div className="h-4 w-32 bg-white/5 animate-pulse rounded"></div>
                            <div className="h-2 w-24 bg-white/5 animate-pulse rounded"></div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ) : selectedEvent ? (
                <div className="relative w-full h-full">
                  <video
                    key={selectedEvent.url}
                    controls
                    autoPlay
                    loop
                    muted
                    className="main-video w-full h-full object-contain bg-black"
                    src={selectedEvent.url}
                  >
                    Your browser does not support the video tag.
                  </video>
                  <div className="absolute top-4 right-4 flex gap-2 z-20">
                    <a
                      href={selectedEvent.url}
                      download
                      className="p-2 bg-emerald-500/20 hover:bg-emerald-500/40 border border-emerald-500/30 rounded-lg text-emerald-400 text-[10px] font-bold tracking-widest flex items-center gap-2"
                    >
                      DOWNLOAD MP4
                    </a>
                  </div>
                  <div className="camera-id-tag">ARCHIVE_{selectedEvent.id.toString().slice(-4)} // PLAYBACK</div>
                </div>
              ) : (
                <div className="video-placeholder group">
                  <div className="relative">
                    <Shield size={64} className="text-white/5 group-hover:text-emerald-500/20 transition-all duration-700 scale-110" />
                    <Video size={32} className="absolute inset-0 m-auto text-emerald-500/40 group-hover:text-emerald-400" />
                  </div>
                  <p className="text-sm tracking-widest text-white/30 group-hover:text-white/50 transition-colors uppercase font-bold">Waiting for stream input...</p>
                </div>
              )}

              <AnimatePresence>
                {selectedEvent && activeTab !== 'cameras' && (
                  <motion.div
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    className="video-metadata-overlay"
                  >
                    <div className={`meta-pill ${selectedEvent.type.toLowerCase() === 'normal' ? 'safe' : 'danger'}`}>
                      <div className="pill-dot"></div>
                      <span>{selectedEvent.type.toUpperCase()}</span>
                    </div>
                    <div className="meta-info">
                      <div className="meta-row"><MapPin size={10} /> <span>{selectedEvent.location}</span></div>
                      <div className="meta-row"><History size={10} /> <span>{selectedEvent.timestamp}</span></div>
                    </div>
                  </motion.div>
                )}
                {isProcessing && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="absolute inset-0 bg-black/60 backdrop-blur-sm z-[30] flex flex-col items-center justify-center"
                  >
                    <div className="relative">
                      <div className="h-16 w-16 border-4 border-emerald-500/20 border-t-emerald-500 rounded-full animate-spin"></div>
                      <Shield className="absolute inset-0 m-auto text-emerald-500 animate-pulse" size={24} />
                    </div>
                    <p className="mt-4 text-emerald-400 font-black tracking-[0.3em] text-[10px] uppercase">AI Source Processing...</p>
                    <p className="text-white/40 text-[9px] mt-1 font-mono">ENCODING_STREAM_NODE_v1.2</p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* AI DETECTION INFORMATION BELOW VIDEO */}
            {linkResult && activeTab === 'dashboard' && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="analysis-info-box mt-4 p-5 glass-morphism rounded-[2rem] border-emerald-500/30 shadow-2xl shadow-emerald-500/5 relative overflow-hidden"
              >
                {/* Background scanning effect */}
                <div className="absolute inset-0 bg-gradient-to-r from-emerald-500/5 to-transparent animate-pulse pointer-events-none" />

                <div className="flex justify-between items-center mb-5 relative z-10">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-emerald-500/20 rounded-lg text-emerald-400">
                      <Shield size={20} />
                    </div>
                    <div>
                      <h4 className="text-xs font-black text-white tracking-[0.3em] uppercase">Intelligence Diagnostic</h4>
                      <p className="text-[10px] text-emerald-400/60 font-mono">NODE_ANALYSIS_COMPLETE_v2.4.1</p>
                    </div>
                  </div>
                  <button onClick={() => setLinkResult(null)} className="p-2 hover:bg-white/5 rounded-full transition-colors text-gray-500"><Settings size={14} /></button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                  <div className="info-stat-premium p-4 rounded-2xl bg-gradient-to-br from-white/[0.03] to-transparent border border-white/5">
                    <p className="text-[10px] text-gray-400 uppercase font-black tracking-widest mb-3">Confidence</p>
                    <div className="flex items-end justify-between">
                      <span className="text-3xl font-black text-emerald-400 tracking-tighter">{Math.round(linkResult.confidence * 100)}%</span>
                      <div className="h-8 w-1 bg-emerald-500/20 rounded-full overflow-hidden">
                        <motion.div initial={{ height: 0 }} animate={{ height: '60%' }} className="w-full bg-emerald-500 bottom-0" />
                      </div>
                    </div>
                  </div>

                  <div className="info-stat-premium p-4 rounded-2xl bg-gradient-to-br from-white/[0.03] to-transparent border border-white/5">
                    <p className="text-[10px] text-gray-400 uppercase font-black tracking-widest mb-3">Threat Level</p>
                    <div className="flex flex-col gap-1">
                      <span className={`text-lg font-black tracking-widest uppercase ${linkResult.prediction.toLowerCase() === 'normal' ? 'text-emerald-400' : 'text-red-500'}`}>
                        {linkResult.prediction.toLowerCase() === 'normal' ? 'Minimal' : 'Elevated'}
                      </span>
                      <span className="text-[10px] text-white/40 font-mono">{linkResult.prediction}</span>
                    </div>
                  </div>

                  <div className="info-stat-premium p-4 rounded-2xl bg-gradient-to-br from-white/[0.03] to-transparent border border-white/5">
                    <p className="text-[10px] text-gray-400 uppercase font-black tracking-widest mb-3">Location Node</p>
                    <div className="flex flex-col gap-1">
                      <span className="text-sm font-bold text-white/80 truncate">{linkResult.location || "ZONE_01"}</span>
                      <span className="text-[10px] text-emerald-400/60 font-mono italic">Geolocation_Active</span>
                    </div>
                  </div>

                  <div className="info-stat-premium p-4 rounded-2xl bg-gradient-to-br from-white/[0.03] to-transparent border border-white/5">
                    <p className="text-[10px] text-gray-400 uppercase font-black tracking-widest mb-3">Encryption</p>
                    <div className="flex items-center gap-2">
                      <Globe size={16} className="text-emerald-500/50" />
                      <span className="text-xs font-mono text-emerald-500/80">AES-256-GCM</span>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </section>

          {/* Map Section */}
          <section className="map-section glass-morphism">
            <div className="section-header">
              <h3>Emergency Response</h3>
              <div className="flex gap-2">
                <div className="status-chip hospital"><Hospital size={14} /></div>
                <div className="status-chip police"><ShieldAlert size={14} /></div>
                <div className="status-chip fire"><Flame size={14} /></div>
              </div>
            </div>

            <div className="map-container overflow-hidden">
              <div className="radar-sweep"></div>
              {locationInfo ? (
                <div className="live-realtime-map">
                  <div className="map-incident-marker" key="marker-main">
                    <div className="marker-ping"></div>
                    <AlertTriangle size={24} color="#ef4444" />
                  </div>

                  {/* Dynamic Nearby services indicators */}
                  {locationInfo.nearby?.hospitals?.map((h, i) => (
                    <div key={`h-${i}`} className="service-marker hospital" style={{
                      top: `${20 + (Math.random() * 30)}%`,
                      left: `${10 + (Math.random() * 30)}%`
                    }}>
                      <Hospital size={16} />
                      <span className="tooltip">{h.name} ({h.distance})</span>
                    </div>
                  ))}
                  {locationInfo.nearby?.police_stations?.map((p, i) => (
                    <div key={`p-marker-${i}-${p.name}`} className="service-marker police" style={{
                      top: `${50 + (Math.random() * 40)}%`,
                      left: `${60 + (Math.random() * 30)}%`
                    }}>
                      <ShieldAlert size={16} />
                      <span className="tooltip">{p.name} ({p.distance})</span>
                    </div>
                  ))}
                  {locationInfo.nearby?.fire_brigade?.map((f, i) => (
                    <div key={`f-${i}`} className="service-marker fire" style={{
                      top: `${10 + (Math.random() * 30)}%`,
                      left: `${50 + (Math.random() * 40)}%`
                    }}>
                      <Flame size={16} />
                      <span className="tooltip">{f.name} ({f.distance})</span>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-muted">
                  <div className="animate-pulse flex flex-col items-center">
                    <Navigation size={32} className="mb-2" />
                    <p>Locating emergency services...</p>
                  </div>
                </div>
              )}
            </div>

            <div className="nearby-services-list">
              <h4>Nearest Facilities ({locationInfo?.address || 'Locating...'})</h4>
              <div className="facility-scroll" style={{ maxHeight: '250px', overflowY: 'auto', paddingRight: '5px' }}>
                {locationInfo?.nearby?.hospitals?.slice(0, 3).map((h, i) => (
                  <div key={`lh-${i}`} className="service-item glass-morphism" style={{ marginBottom: '8px', borderLeft: '4px solid #60a5fa' }}>
                    <Hospital size={18} className="text-blue-400" />
                    <div className="service-meta">
                      <p className="service-name">{h.name}</p>
                      <p className="service-dist">{h.distance}</p>
                    </div>
                    <Navigation size={18} className="nav-btn" />
                  </div>
                ))}
                {locationInfo?.nearby?.police_stations?.slice(0, 3).map((p, i) => (
                  <div key={`lp-${i}`} className="service-item glass-morphism" style={{ marginBottom: '8px', borderLeft: '4px solid #34d399' }}>
                    <ShieldAlert size={18} className="text-green-400" />
                    <div className="service-meta">
                      <p className="service-name">{p.name}</p>
                      <p className="service-dist">{p.distance}</p>
                    </div>
                    <Navigation size={18} className="nav-btn" />
                  </div>
                ))}
                {locationInfo?.nearby?.fire_brigade?.slice(0, 3).map((f, i) => (
                  <div key={`lf-${i}`} className="service-item glass-morphism" style={{ marginBottom: '8px', borderLeft: '4px solid #fb7185' }}>
                    <Flame size={18} className="text-rose-400" />
                    <div className="service-meta">
                      <p className="service-name">{f.name}</p>
                      <p className="service-dist">{f.distance}</p>
                    </div>
                    <Navigation size={18} className="nav-btn" />
                  </div>
                ))}
                {(!locationInfo?.nearby?.hospitals?.length && !locationInfo?.nearby?.police_stations?.length && !locationInfo?.nearby?.fire_brigade?.length) && locationInfo && (
                  <p className="text-muted text-xs text-center p-4">Searching for facilities within 5km...</p>
                )}
              </div>
            </div>
          </section>

          {/* Alert History Section */}
          <section className="history-section glass-morphism">
            <div className="section-header">
              <h3>Detection Logs</h3>
              <button className="text-btn">View All</button>
            </div>

            <div className="event-list">
              {events.map((event) => (
                <motion.div
                  key={event.id}
                  whileHover={{ x: 5 }}
                  className={`event-card ${selectedEvent?.id === event.id ? 'active' : ''}`}
                  onClick={() => setSelectedEvent(event)}
                >
                  <div className={`event-icon ${event.type}`}>
                    {event.type === 'fighting' && <AlertTriangle size={18} />}
                    {event.type === 'roadaccident' && <AlertTriangle size={18} />}
                    {event.type === 'robbery' && <ShieldAlert size={18} />}
                    {event.type === 'explosion' && <Flame size={18} />}
                    {event.type === 'normal' && <Shield size={18} />}
                    {(event.type === 'analysis' || event.type === 'alert') && <Shield size={18} className="opacity-50" />}
                  </div>
                  <div className="event-info">
                    <div className="flex justify-between items-start">
                      <p className="event-title text-capitalize">{event.type}</p>
                      <span className="event-time">{event.timestamp.split('_')[1]}</span>
                    </div>
                    <p className="event-loc">{event.location}</p>
                  </div>
                </motion.div>
              ))}
            </div>
          </section>
        </div>
      </main>

      <style>
        {`
        .app-container {
          display: flex;
          height: 100vh;
          width: 100vw;
          background-color: var(--bg-deep);
        }

        .sidebar {
          width: 260px;
          height: 100%;
          display: flex;
          flex-direction: column;
          padding: 2rem 1.5rem;
          border-right: 1px solid var(--border);
          z-index: 10;
        }

        .logo-container {
          display: flex;
          flex-direction: column;
          margin-bottom: 3rem;
        }

        .logo-icon {
          color: var(--accent);
          filter: drop-shadow(0 0 8px var(--accent-glow));
          margin-bottom: 0.5rem;
        }

        .logo-text {
          font-size: 1.5rem;
          font-weight: 700;
          letter-spacing: 2px;
          color: #fff;
        }

        .logo-subtext {
          font-size: 0.7rem;
          color: var(--text-muted);
          letter-spacing: 1px;
        }

        .nav-links {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
          flex-grow: 1;
        }

        .nav-item {
          display: flex;
          align-items: center;
          gap: 1rem;
          padding: 0.8rem 1rem;
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          border-radius: 12px;
          font-weight: 500;
          transition: all 0.3s ease;
          width: 100%;
          text-align: left;
        }

        .nav-item:hover {
          background: rgba(255, 255, 255, 0.05);
          color: #fff;
        }

        .nav-item.active {
          background: var(--accent-glow);
          color: var(--accent);
          border-right: 3px solid var(--accent);
        }

        .user-profile {
          display: flex;
          align-items: center;
          gap: 1rem;
          margin-top: 2rem;
          padding-top: 2rem;
          border-top: 1px solid var(--border);
        }

        .avatar {
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 50%;
        }

        .user-name {
          font-size: 0.9rem;
          font-weight: 600;
        }

        .user-status {
          font-size: 0.75rem;
          color: var(--accent);
          font-weight: 700;
          letter-spacing: 1px;
        }

        .nav-icon-box {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 32px;
          height: 32px;
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.03);
          transition: all 0.3s;
        }

        .nav-item.active .nav-icon-box {
          background: var(--accent);
          color: #000;
          box-shadow: 0 0 15px var(--accent-glow);
        }

        .main-content {
          flex-grow: 1;
          display: flex;
          flex-direction: column;
          padding: 1.5rem;
          overflow-y: auto;
          gap: 1.5rem;
        }

        .top-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 0.8rem 2rem;
          border-radius: 20px;
          gap: 2rem;
        }

        .system-metrics {
          display: flex;
          gap: 1.5rem;
        }

        .metric {
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .metric .label {
          font-size: 0.6rem;
          color: var(--text-muted);
          font-weight: 800;
          letter-spacing: 1px;
        }

        .metric .value {
          font-size: 0.85rem;
          font-weight: 700;
          font-family: 'JetBrains Mono', monospace;
          color: var(--accent);
          text-shadow: 0 0 10px var(--accent-glow);
        }

        .search-bar {
          display: flex;
          align-items: center;
          gap: 1rem;
          background: rgba(255, 255, 255, 0.03);
          padding: 0.6rem 1.2rem;
          border-radius: 100px;
          width: 400px;
          border: 1px solid var(--border);
        }

        .search-bar form { width: 100%; }

        .search-bar input {
          background: transparent;
          border: none;
          color: #fff;
          width: 100%;
          outline: none;
          font-size: 0.9rem;
        }

        .header-icon-btn {
          width: 40px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 12px;
          position: relative;
          cursor: pointer;
        }

        .badge {
          position: absolute;
          top: 8px;
          right: 8px;
          width: 8px;
          height: 8px;
          background: var(--accent);
          border-radius: 50%;
          box-shadow: 0 0 10px var(--accent);
        }

        .dashboard-grid {
          display: grid;
          grid-template-columns: 2fr 1fr;
          grid-template-rows: auto auto;
          gap: 1.5rem;
          height: calc(100% - 100px);
        }

        .live-feed-section {
          padding: 1.5rem;
          border-radius: 24px;
          display: flex;
          flex-direction: column;
          gap: 1.5rem;
          grid-row: span 1;
        }

        .section-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
        }

        .video-player-container {
          position: relative;
          width: 100%;
          aspect-ratio: 16/9;
          background: #000;
          border-radius: 24px;
          overflow: hidden;
          border: 1px solid var(--border);
          box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
        }

        .scan-line {
          position: absolute;
          top: 0;
          left: 0;
          width: 100%;
          height: 2px;
          background: linear-gradient(90deg, transparent, var(--accent), transparent);
          opacity: 0.2;
          z-index: 15;
          animation: scan 4s linear infinite;
          pointer-events: none;
        }

        @keyframes scan {
          0% { top: 0; }
          100% { top: 100%; }
        }

        .camera-id-tag {
          position: absolute;
          top: 1.5rem;
          left: 1.5rem;
          background: rgba(0, 0, 0, 0.5);
          backdrop-filter: blur(4px);
          padding: 0.4rem 0.8rem;
          border-radius: 6px;
          font-family: 'JetBrains Mono', monospace;
          font-size: 0.65rem;
          color: rgba(255, 255, 255, 0.8);
          border: 1px solid rgba(255, 255, 255, 0.1);
          z-index: 10;
          letter-spacing: 2px;
        }

        .main-video {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }

        .video-placeholder {
          height: 100%;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 1rem;
          color: var(--text-muted);
        }

        .video-metadata-overlay {
          position: absolute;
          bottom: 1.5rem;
          left: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1rem;
          z-index: 20;
        }

        .meta-pill {
          display: flex;
          align-items: center;
          gap: 0.6rem;
          padding: 0.5rem 1.2rem;
          border-radius: 100px;
          backdrop-filter: blur(10px);
          font-size: 0.7rem;
          font-weight: 800;
          letter-spacing: 2px;
          border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .meta-pill.safe { background: rgba(16, 185, 129, 0.2); color: #10b981; }
        .meta-pill.danger { background: rgba(239, 68, 68, 0.2); color: #ef4444; }

        .pill-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: currentColor;
          box-shadow: 0 0 8px currentColor;
        }

        .meta-info {
          background: rgba(0, 0, 0, 0.4);
          backdrop-filter: blur(10px);
          padding: 1rem;
          border-radius: 16px;
          border: 1px solid rgba(255, 255, 255, 0.05);
          display: flex;
          flex-direction: column;
          gap: 0.4rem;
        }

        .meta-row {
          display: flex;
          align-items: center;
          gap: 0.6rem;
          font-size: 0.75rem;
          color: rgba(255, 255, 255, 0.6);
        }

        .map-section {
          padding: 1.5rem;
          border-radius: 24px;
          display: flex;
          flex-direction: column;
          gap: 1.2rem;
        }

        .map-container {
          width: 100%;
          height: 250px;
          background: #1a1a1c;
          border-radius: 16px;
          position: relative;
          overflow: hidden;
          background-image: radial-gradient(circle at 2px 2px, #2a2a2c 1px, transparent 0);
          background-size: 20px 20px;
        }

        .mock-map {
          width: 100%;
          height: 100%;
          position: relative;
        }

        .map-incident-marker {
          position: absolute;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          z-index: 5;
        }

        .radar-sweep {
          position: absolute;
          width: 200%;
          height: 200%;
          top: -50%;
          left: -50%;
          background: conic-gradient(from 0deg, transparent, rgba(16, 185, 129, 0.1), transparent 30deg);
          animation: rotate 4s linear infinite;
          z-index: 2;
          pointer-events: none;
        }

        @keyframes rotate {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }

        .marker-ping {
          position: absolute;
          width: 40px;
          height: 40px;
          background: rgba(239, 68, 68, 0.3);
          border-radius: 50%;
          animation: pulse-ping 2s infinite;
          top: -8px;
          left: -8px;
        }

        @keyframes pulse-ping {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(3); opacity: 0; }
        }

        .service-marker {
          position: absolute;
          padding: 0.4rem;
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: 8px;
          cursor: help;
        }

        .service-marker.hospital { color: #60a5fa; }
        .service-marker.police { color: #34d399; }
        .service-marker.fire { color: #fb7185; }

        .service-marker .tooltip {
          position: absolute;
          bottom: 100%;
          left: 50%;
          transform: translateX(-50%);
          background: #000;
          color: #fff;
          padding: 0.2rem 0.6rem;
          border-radius: 4px;
          font-size: 0.6rem;
          white-space: nowrap;
          opacity: 0;
          transition: 0.3s;
        }

        .service-marker:hover .tooltip { opacity: 1; }

        .nearby-services-list {
          display: flex;
          flex-direction: column;
          gap: 0.8rem;
        }

        .service-item {
          display: flex;
          align-items: center;
          gap: 1rem;
          padding: 0.8rem 1rem;
          border-radius: 12px;
        }

        .service-meta { flex-grow: 1; }
        .service-name { font-size: 0.85rem; font-weight: 600; }
        .service-dist { font-size: 0.75rem; color: var(--text-muted); }
        .nav-btn { color: var(--accent); cursor: pointer; }

        .history-section {
          padding: 1.5rem;
          border-radius: 24px;
          grid-column: 1 / 3;
          display: flex;
          flex-direction: column;
          gap: 1.2rem;
        }

        .event-list {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
          gap: 1rem;
        }

        .event-card {
          display: flex;
          align-items: center;
          gap: 1rem;
          padding: 1rem;
          background: rgba(255, 255, 255, 0.02);
          border-radius: 16px;
          border: 1px solid var(--border);
          cursor: pointer;
          transition: all 0.3s ease;
        }

        .event-card:hover {
          background: rgba(255, 255, 255, 0.05);
          border-color: var(--accent);
        }

        .event-card.active {
          background: var(--accent-glow);
          border-color: var(--accent);
        }

        .event-icon {
          width: 44px;
        }

        .report-modal-overlay {
          position: fixed;
          inset: 0;
          z-index: 100;
          background: rgba(0, 0, 0, 0.7);
          backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .report-modal {
          width: 90%;
          max-width: 650px;
          background: #111113;
          padding: 2rem;
          border-radius: 20px;
          border: 1px solid var(--accent);
          box-shadow: 0 0 40px rgba(16, 185, 129, 0.15);
        }

        .event-icon { 
          width: 44px; 
          height: 44px;
          border-radius: 12px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .event-icon.fighting { background: rgba(239, 68, 68, 0.1); color: #ef4444; }
        .event-icon.roadaccident { background: rgba(245, 158, 11, 0.1); color: #f59e0b; }
        .event-icon.robbery { background: rgba(16, 185, 129, 0.1); color: #10b981; }
        .event-icon.explosion { background: rgba(239, 68, 68, 0.2); color: #ef4444; }
        .event-icon.normal { background: rgba(16, 185, 129, 0.1); color: #10b981; }
        .event-icon.analysis { background: rgba(168, 85, 247, 0.1); color: #a855f7; }
        .event-icon.alert { background: rgba(255, 255, 255, 0.05); color: #fff; }

        .event-info { flex-grow: 1; }
        .event-title { font-weight: 600; font-size: 0.95rem; }
        .event-time { font-size: 0.75rem; color: var(--text-muted); }
        .event-loc { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.2rem; }

        .flex { display: flex; }
        .items-center { align-items: center; }
        .gap-2 { gap: 0.5rem; }
        .text-muted { color: var(--text-muted); }
        .text-sm { font-size: 0.8rem; }
        .text-capitalize { text-transform: capitalize; }
        .justify-between { justify-content: space-between; }
        .items-start { align-items: flex-start; }

        .status-chip {
          width: 28px;
          height: 28px;
          border-radius: 50%;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .status-chip.hospital { background: rgba(96, 165, 250, 0.1); color: #60a5fa; }
        .status-chip.police { background: rgba(52, 211, 153, 0.1); color: #34d399; }
        .status-chip.fire { background: rgba(251, 113, 133, 0.1); color: #fb7185; }

        .alert-badge-mini {
          display: flex;
          align-items: center;
          gap: 4px;
          background: #ef4444;
          color: white;
          font-size: 10px;
          padding: 2px 6px;
          border-radius: 4px;
          font-weight: 800;
          width: fit-content;
        }

        .live-realtime-map {
          width: 100%;
          height: 100%;
          position: relative;
          background: #09090b;
        }

        .analysis-info-box {
          background: rgba(16, 185, 129, 0.05);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(16, 185, 129, 0.2);
          transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .analysis-info-box:hover {
          border-color: rgba(16, 185, 129, 0.4);
          box-shadow: 0 0 30px rgba(16, 185, 129, 0.1);
        }

        .info-stat-premium {
          transition: transform 0.3s ease;
        }

        .info-stat-premium:hover {
          transform: translateY(-2px);
          background: rgba(255, 255, 255, 0.05);
        }

        @keyframes pulse {
          0% { transform: scale(1); opacity: 0.5; }
          50% { transform: scale(1.5); opacity: 0; }
          100% { transform: scale(1); opacity: 0.5; }
        }
      `}</style>
    </div>
  );
};

export default App;
