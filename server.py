import sys
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os
import json
import yaml
import time
import requests
import cv2
import base64
import numpy as np
from PIL import Image
import torch
import io
from datetime import datetime
from pathlib import Path
import uvicorn
from pydantic import BaseModel
from contextlib import asynccontextmanager
import socket
import platform

# Import VideoPredictor from detect.py
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from detect import LocationService, VideoPredictor

# Global predictor instance
predictor = None
location_service = LocationService()
background_tasks_status = {} # Track status of video processing

def get_real_nearby(lat, lng):
    """Fetch real nearby facilities using Overpass API (OpenStreetMap)"""
    try:
        overpass_url = "http://overpass-api.de/api/interpreter"
        overpass_query = f"""
        [out:json];
        (
          node["amenity"="hospital"](around:5000,{lat},{lng});
          node["amenity"="police"](around:5000,{lat},{lng});
          node["amenity"="fire_station"](around:5000,{lat},{lng});
        );
        out body;
        """
        response = requests.get(overpass_url, params={'data': overpass_query}, timeout=10, verify=False)
        if response.status_code == 200:
            data = response.json()
            elements = data.get('elements', [])
            services = {"hospitals": [], "police_stations": [], "fire_brigade": []}
            for el in elements:
                name = el.get('tags', {}).get('name', 'Unnamed Facility')
                etype = el.get('tags', {}).get('amenity')
                flat, flng = el.get('lat'), el.get('lon')
                dist = ((flat - lat)**2 + (flng - lng)**2)**0.5 * 111
                item = {"name": name, "distance": f"{dist:.1f}km", "coords": [flat, flng]}
                if etype == "hospital": services["hospitals"].append(item)
                elif etype == "police": services["police_stations"].append(item)
                elif etype == "fire_station": services["fire_brigade"].append(item)
            return services
    except Exception as e: 
        print(f"⚠️ Nearby facility search skipped or failed: {e}")
    return {"hospitals": [], "police_stations": [], "fire_brigade": []}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global predictor
    print("-----------------------------------------")
    print("AVTAR SMART SECURITY - SYSTEM STARTING...")
    print("-----------------------------------------")
    try:
        predictor = VideoPredictor(
            model_path=str(BASE_DIR / "runs_ucf" / "best_model.pth"),
            config_path=str(BASE_DIR / "config.yaml"),
            pushbullet_api_key=os.getenv("PUSHBULLET_API_KEY", "")
        )
        # Match alphabetical order as seen in confusion matrix for 4-class model: [Explosion, Fighting, RoadAccident, Robbery]
        # Adding 'Normal' as a logical 5th class for the HUD logic
        predictor.classes = ["Explosion", "Fighting", "RoadAccident", "Robbery", "Normal"]
        print(f"✅ AI ENGINE: Classes calibrated to {predictor.classes}")
        print("✅ YOLO ENGINE: Ultralytics YOLOv8 loaded")
    except Exception as e:
        print(f"❌ FAILED TO LOAD ENGINES: {e}")
    yield
    print("Shutting down...")

app = FastAPI(lifespan=lifespan)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
DETECTED_EVENTS_DIR = BASE_DIR / "detected_events"
DETECTED_EVENTS_DIR.mkdir(exist_ok=True)

# Mount static files
app.mount("/videos", StaticFiles(directory=str(DETECTED_EVENTS_DIR)), name="videos")
app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="root_static")

class VideoLink(BaseModel):
    url: str

@app.get("/")
async def root():
    return {"status": "online", "system": "AVTAR Smart Security", "version": "1.2.0"}

@app.get("/api/video_status/{filename}")
async def get_video_status(filename: str):
    """Check if a video file is ready"""
    path = DETECTED_EVENTS_DIR / filename
    status = background_tasks_status.get(filename, "unknown")
    
    if status == "ready" and path.exists():
        return {"status": "ready", "url": f"http://localhost:8000/videos/{filename}?t={int(time.time())}"}
    if status.startswith("error"):
        return {"status": "error"}
    return {"status": "processing"}

@app.get("/api/events")
async def get_events():
    events = []
    try:
        video_files = list(DETECTED_EVENTS_DIR.glob("*.mp4")) + list(DETECTED_EVENTS_DIR.glob("*.avi"))
        video_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        loc = location_service.get_current_location()
        address = loc.get('address', 'Unknown')
        
        t = int(time.time())
        for file in video_files[:40]:
            try:
                parts = file.stem.split("_")
                event_type = parts[0].lower()
                
                valid_types = ["fighting", "roadaccident", "robbery", "explosion", "normal"]
                if event_type not in valid_types:
                    event_type = "analysis" if event_type == "proc" else "alert"
                
                events.append({
                    "id": file.name,
                    "type": event_type,
                    "timestamp": datetime.fromtimestamp(os.path.getmtime(file)).strftime("%Y-%m-%d %H:%M:%S"),
                    "url": f"http://localhost:8000/videos/{file.name}?t={t}",
                    "location": address,
                    "device": "Security Node 01",
                    "status": "Verified"
                })
            except: continue
    except Exception as e:
        print(f"Error fetching events: {e}")
    return events

async def analyze_and_process(url_clean: str, processed_path: Path, prediction: str, confidence: float, task_id: str):
    """Heavy lifting video processing run in background"""
    background_tasks_status[task_id] = "processing"
    try:
        cap = cv2.VideoCapture(url_clean)
        if not cap.isOpened():
             background_tasks_status[task_id] = "error"
             return

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        
        # Try various codecs, prioritizing ones that work on Windows
        fourcc_options = [
            ('avc1', '.mp4'),  # Browser standard
            ('mp4v', '.mp4'),  # Windows standard
            ('H264', '.mp4'),  
            ('MJPG', '.mp4')
        ]
        
        out = None
        for codec, _ in fourcc_options:
            try:
                fourcc = cv2.VideoWriter_fourcc(*codec)
                out = cv2.VideoWriter(str(processed_path), fourcc, fps, (width, height))
                if out and out.isOpened():
                    print(f"🎬 [SUCCESS] VideoWriter using codec: {codec}")
                    break
            except: 
                continue
        
        if not out or not out.isOpened():
            print("❌ [CRITICAL] All codecs failed. Creating empty marker.")
            background_tasks_status[task_id] = "error"
            return
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        max_frames = min(total_frames, 1200) 
        frame_count = 0  # Re-adding the missing counter
        
        # Sliding Window for local inference
        window_buffer = []
        local_prediction = "Normal"
        local_confidence = 1.0
        prediction_history = [] # Re-added to prevent NameError
        
        last_annotated = None
        
        while cap.isOpened() and frame_count < max_frames:
            ret, frame = cap.read()
            if not ret: break
            
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb_frame)
            window_buffer.append(pil_img)
            
            # Keep buffer size consistent with model expectations (usually 16 frames)
            if len(window_buffer) > 16:
                window_buffer.pop(0)

            # Performance: run detection every 2nd frame
            if frame_count % 2 == 0 or last_annotated is None:
                last_annotated, _ = predictor.detector.detect(frame)
            
            # Local Classification: Every 16 frames
            if frame_count % 16 == 0 and len(window_buffer) == 16:
                try:
                    clip = predictor.preprocess_frames(window_buffer)
                    with torch.no_grad():
                        outputs = predictor.model(clip)
                        probs = torch.softmax(outputs, dim=1)
                        conf, pred = torch.max(probs, 1)
                        
                    predicted_class = predictor.classes[pred.item()]
                    conf_val = conf.item()
                    
                    # High Threshold (90%) for Anomaly Detection to prevent false positives
                    if conf_val > 0.90:
                        local_prediction = predicted_class
                        local_confidence = conf_val
                        prediction_history.append(local_prediction)
                    else:
                        local_prediction = "Normal"
                        local_confidence = 1.0 - conf_val
                except Exception as e:
                    print(f"Local inference error: {e}")

            annotated_frame = last_annotated.copy()
            h, w = annotated_frame.shape[:2]
            
            # Professional HUD State Logic
            if frame_count < 30:
                local_prediction = "Normal"
                local_confidence = 0.99
            
            is_anomaly = local_prediction.lower() != "normal"
            display_color = (0, 0, 255) if is_anomaly else (0, 210, 0)
            
            # HUD Box
            overlay = annotated_frame.copy()
            cv2.rectangle(overlay, (0, 0), (int(w*0.5), 100), (10, 10, 10), -1)
            cv2.addWeighted(overlay, 0.85, annotated_frame, 0.15, 0, annotated_frame)
            
            # Status Text
            status_text = f"AI LIVE :: {local_prediction.upper()}"
            if local_prediction.lower() == "normal":
                status_text = "AI STATUS :: SECURE"
            
            cv2.putText(annotated_frame, status_text, (20, 35), cv2.FONT_HERSHEY_DUPLEX, 0.7, display_color, 2)
            cv2.putText(annotated_frame, f"THRESHOLD :: {local_confidence:.2%}", (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            cv2.putText(annotated_frame, f"NODE_01 :: MONITORING_SCAN", (20, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1)
            
            # Dynamic Scanning Line (Visual Effect)
            scan_y = int((frame_count * 10) % h)
            cv2.line(annotated_frame, (0, scan_y), (w, scan_y), display_color, 1)
            
            out.write(annotated_frame)
            frame_count += 1
            
        cap.release()
        out.release()
        time.sleep(1) 
        background_tasks_status[task_id] = "ready"
        print(f"✅ Analysis Complete: {task_id}")
    except Exception as e:
        background_tasks_status[task_id] = f"error: {str(e)}"
        print(f"Background processing error: {e}")

@app.post("/api/process_link")
async def process_link(video: VideoLink, background_tasks: BackgroundTasks):
    if not predictor: return {"error": "AI not initialized"}
    
    url_raw = video.url.strip('"').strip("'")
    url_clean = url_raw
    
    # Try common extensions if file not found
    if not os.path.exists(url_clean):
        for ext in ['.mp4', '.avi', '.mov', '.mkv']:
            if os.path.exists(url_raw + ext):
                url_clean = url_raw + ext
                break
    
    if not os.path.exists(url_clean):
        print(f"❌ FILE NOT FOUND: {url_raw}")
        raise HTTPException(status_code=404, detail=f"Source not found: {url_raw}")

    print(f"📡 ANALYZING: {url_clean}")
    
    # Standardize Anomaly names
    prediction_map = {
        "roadaccidents": "RoadAccident",
        "fighting": "Fighting",
        "robbery": "Robbery",
        "explosion": "Explosion",
        "abuse": "Abuse",
        "arrest": "Arrest",
        "assault": "Assault",
        "burglary": "Burglary",
        "roadaccident": "RoadAccident",
        "shooting": "Shooting",
        "shoplifting": "Shoplifting",
        "stealing": "Stealing",
        "vandalism": "Vandalism"
    }
    
    # 1. Run Action Classification
    try:
        prediction, confidence, _ = predictor.predict_video(url_clean)
        
        # Professional-Grade Thresholding for Global Report
        if confidence < 0.90:
            prediction = "Normal"
            confidence = 1.0 - (confidence / 2)
            
    except Exception as e:
        print(f"Classification error: {e}")
        prediction, confidence = "Unknown", 0.0

    # Clean location coordinates for nearby search
    loc = location_service.get_current_location()
    coords = loc.get('coordinates', '13.34,74.74')
    if not coords or coords == 'None':
        coords = '13.34,74.74'
    
    try:
        lat, lng = map(float, coords.split(','))
    except:
        lat, lng = 13.34, 74.74

    nearby_data = get_real_nearby(lat, lng)

    # 2. Queue background video processing
    timestamp = int(time.time())
    processed_video_name = f"{prediction.lower()}_{timestamp}.mp4"
    processed_path = DETECTED_EVENTS_DIR / processed_video_name
    
    background_tasks.add_task(analyze_and_process, url_clean, processed_path, prediction, confidence, processed_video_name)

    return {
        "message": f"Intelligence report generated for {prediction}",
        "prediction": str(prediction),
        "confidence": float(confidence),
        "status": "success",
        "task_id": processed_video_name,
        "laptop": socket.gethostname(),
        "location": str(loc.get('address', 'Detection Zone 01')),
        "nearby_facilities": nearby_data,
        "video_url": f"http://localhost:8000/videos/{processed_video_name}?t={timestamp}"
    }

@app.websocket("/api/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    if not predictor:
        await websocket.close(code=1001, reason="AI not ready")
        return
        
    buffer = []
    try:
        while True:
            data = await websocket.receive_text()
            header, encoded = data.split(",", 1)
            image_data = base64.b64decode(encoded)
            image = Image.open(io.BytesIO(image_data)).convert('RGB')
            buffer.append(image)
            
            # YOLO detection on current frame for live feedback
            cv2_img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            annotated_frame, _ = predictor.detector.detect(cv2_img)
            _, encoded_img = cv2.imencode('.jpg', annotated_frame)
            b64_img = base64.b64encode(encoded_img).decode('utf-8')

            if len(buffer) >= 16:
                clip = predictor.preprocess_frames(buffer)
                with torch.no_grad():
                    outputs = predictor.model(clip)
                    probabilities = torch.softmax(outputs, dim=1)
                    confidence, predicted = torch.max(probabilities, 1)
                
                predicted_class = predictor.classes[predicted.item()]
                conf_val = confidence.item()
                if conf_val < 0.85: predicted_class = "Normal"
                
                await websocket.send_json({
                    "status": "detected",
                    "class": predicted_class,
                    "confidence": float(conf_val) if predicted_class != "Normal" else float(1.0 - conf_val),
                    "image": b64_img
                })
                buffer = buffer[8:]
            else:
                await websocket.send_json({"status": "buffering", "count": len(buffer), "image": b64_img})
                
    except WebSocketDisconnect: pass
    except Exception as e: print(f"WS Error: {e}")

@app.get("/api/location")
async def get_location():
    loc = location_service.get_current_location()
    return loc

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
