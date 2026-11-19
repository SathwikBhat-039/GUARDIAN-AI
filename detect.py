import torch
import torch.nn as nn
from torchvision import transforms
import cv2
import numpy as np
from PIL import Image
import yaml
import os
import torchvision.models as models
import random
import requests
import time
import json
from pathlib import Path
from ultralytics import YOLO
from datetime import datetime
import socket
import subprocess
import platform
import struct

def resolve_hostname(hostname):
    """Attempts to resolve hostname using system DNS, with a fallback to Google DNS (8.8.8.8)"""
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        # Fallback: Manual DNS query to 8.8.8.8 (Google DNS)
        try:
            print(f"⚠️ System DNS failed for {hostname}, trying Google DNS fallback...")
            # Simple UDP DNS query for A record
            query = b'\xaa\xaa\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00' # Header
            for part in hostname.split('.'):
                query += struct.pack("B", len(part)) + part.encode('utf-8')
            query += b'\x00\x00\x01\x00\x01' # Type A, Class IN
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(3)
            sock.sendto(query, ("8.8.8.8", 53))
            data, _ = sock.recvfrom(512)
            
            # Very basic parsing of the first A record in the response
            # Note: This is a simplified resolver for emergencies
            off = len(query)
            # Skip name (compression usually points back to query name at offset 12)
            ans_type, ans_class, ttl, rdlen = struct.unpack("!HHIH", data[off+2:off+12])
            if ans_type == 1: # A record
                ip = socket.inet_ntoa(data[off+12:off+12+rdlen])
                print(f"✅ Resolved {hostname} to {ip} via Google DNS")
                return ip
        except Exception as e:
            print(f"❌ DNS fallback failed: {e}")
    return hostname # Return name if resolution fails completely

class LocationService:
    def __init__(self, manual_location=None):
        self.last_location = None
        self.last_location_time = 0
        self.cache_duration = 3600  # Cache location for 1 hour
        self.manual_location = manual_location
    
    def get_current_location(self):
        """Get current location using manual override or multiple auto methods"""
        if self.manual_location:
            return {
                'success': True,
                'address': self.manual_location,
                'map_url': f"https://www.google.com/maps/search/{requests.utils.quote(self.manual_location)}",
                'coordinates': 'Manual',
                'method': 'config_manual_override'
            }
        
        current_time = time.time()
        
        # Return cached location if still valid
        if (self.last_location and 
            (current_time - self.last_location_time) < self.cache_duration):
            return self.last_location
        
        try:
            # Method 1: Try ipinfo.io first
            location = self._get_location_ipinfo()
            if location and location.get('success'):
                self.last_location = location
                self.last_location_time = current_time
                return location
            
            # Method 2: Try ipapi.co as fallback
            location = self._get_location_ipapi()
            if location and location.get('success'):
                self.last_location = location
                self.last_location_time = current_time
                return location
            
            # Method 3: Try abstractapi as second fallback
            location = self._get_location_abstractapi()
            if location and location.get('success'):
                self.last_location = location
                self.last_location_time = current_time
                return location
            
            # If all methods fail, return error
            return {
                'success': False,
                'address': 'Location service unavailable',
                'map_url': 'https://maps.google.com',
                'coordinates': None,
                'method': 'failed'
            }
            
        except Exception as e:
            return {
                'success': False,
                'address': f'Location error: {str(e)}',
                'map_url': 'https://maps.google.com',
                'coordinates': None,
                'method': 'error'
            }
    
    def _reverse_geocode(self, lat, lng):
        """Convert coordinates to a detailed address using OpenStreetMap Nominatim"""
        try:
            # Nominatim requires a user-agent to avoid 403
            headers = {'User-Agent': 'AvtarSmartSurveillance/1.2'}
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}"
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                display_name = data.get('display_name')
                if display_name:
                    return display_name
        except Exception as e:
            print(f"Reverse geocode failed: {str(e)}")
        return None

    def _get_location_ipinfo(self):
        """Get location using ipinfo.io"""
        try:
            response = requests.get("https://ipinfo.io/json", timeout=10, verify=False)
            if response.status_code == 200:
                data = response.json()
                loc = data.get("loc", "").split(",")  # "lat,lng" format
                city = data.get("city", "")
                region = data.get("region", "")
                country = data.get("country", "")
                org = data.get("org", "")
                
                if len(loc) == 2:
                    lat, lng = loc
                    map_url = f"https://www.google.com/maps?q={lat},{lng}"
                    
                    # Enhanced location: Try reverse geocoding for street-level accuracy
                    detailed_address = self._reverse_geocode(lat, lng)
                    address = detailed_address if detailed_address else f"{city}, {region}, {country}"
                    
                    return {
                        'success': True,
                        'address': address,
                        'map_url': map_url,
                        'coordinates': f"{lat},{lng}",
                        'city': city,
                        'region': region,
                        'country': country,
                        'isp': org,
                        'method': 'ipinfo.io' + (' + reverse_geocoding' if detailed_address else '')
                    }
        except Exception as e:
            print(f"ipinfo.io failed: {str(e)}")
        
        return {'success': False}
    
    def _get_location_ipapi(self):
        """Get location using ipapi.co"""
        try:
            response = requests.get("https://ipapi.co/json/", timeout=10, verify=False)
            if response.status_code == 200:
                data = response.json()
                lat = data.get("latitude")
                lng = data.get("longitude")
                city = data.get("city", "")
                region = data.get("region", "")
                country = data.get("country_name", "")
                isp = data.get("org", "")
                
                if lat and lng:
                    map_url = f"https://www.google.com/maps?q={lat},{lng}"
                    
                    # Enhanced location: Try reverse geocoding for street-level accuracy
                    detailed_address = self._reverse_geocode(lat, lng)
                    address = detailed_address if detailed_address else f"{city}, {region}, {country}"
                    
                    return {
                        'success': True,
                        'address': address,
                        'map_url': map_url,
                        'coordinates': f"{lat},{lng}",
                        'city': city,
                        'region': region,
                        'country': country,
                        'isp': isp,
                        'method': 'ipapi.co' + (' + reverse_geocoding' if detailed_address else '')
                    }

        except Exception as e:
            print(f"ipapi.co failed: {str(e)}")
        
        return {'success': False}
    
    def _get_location_abstractapi(self):
        """Get location using abstractapi.com"""
        try:
            # Free tier API key - you might want to get your own
            response = requests.get(
                f"https://ipgeolocation.abstractapi.com/v1/?api_key={os.getenv('ABSTRACTAPI_KEY', '')}",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                lat = data.get("latitude")
                lng = data.get("longitude")
                city = data.get("city", "")
                region = data.get("region", "")
                country = data.get("country", "")
                
                if lat and lng:
                    map_url = f"https://www.google.com/maps?q={lat},{lng}"
                    address = f"{city}, {region}, {country}"
                    
                    return {
                        'success': True,
                        'address': address,
                        'map_url': map_url,
                        'coordinates': f"{lat},{lng}",
                        'city': city,
                        'region': region,
                        'country': country,
                        'method': 'abstractapi'
                    }
        except Exception as e:
            print(f"abstractapi failed: {str(e)}")
        
        return {'success': False}
    
    def get_network_info(self):
        """Get additional network information"""
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            
            # Get public IP
            public_ip_response = requests.get("https://api.ipify.org", timeout=5)
            public_ip = public_ip_response.text.strip() if public_ip_response.status_code == 200 else "Unknown"
            
            return {
                'hostname': hostname,
                'local_ip': local_ip,
                'public_ip': public_ip,
                'platform': platform.platform()
            }
        except Exception as e:
            return {
                'hostname': 'Unknown',
                'local_ip': 'Unknown',
                'public_ip': 'Unknown',
                'platform': platform.platform()
            }

class VideoClassifier(nn.Module):
    def __init__(self, num_classes, backbone="resnet18", hidden_size=256, num_lstm_layers=1,
                 bidirectional=True, dropout=0.3, freeze_backbone=False):
        super().__init__()
        if backbone == "resnet18":
            self.cnn = models.resnet18(pretrained=True)
            feat_dim = 512
        elif backbone == "resnet34":
            self.cnn = models.resnet34(pretrained=True)
            feat_dim = 512
        elif backbone == "resnet50":
            self.cnn = models.resnet50(pretrained=True)
            feat_dim = 2048
        elif backbone == "efficientnet_b0":
            self.cnn = models.efficientnet_b0(pretrained=True)
            feat_dim = 1280
        else:
            raise ValueError(f"Unsupported backbone: {backbone}")
        self.cnn = nn.Sequential(*list(self.cnn.children())[:-1])
        if freeze_backbone:
            for p in self.cnn.parameters():
                p.requires_grad = False
        self.lstm = nn.LSTM(
            input_size=feat_dim,
            hidden_size=hidden_size,
            num_layers=num_lstm_layers,
            bidirectional=bidirectional,
            dropout=dropout,
            batch_first=True
        )
        lstm_out_dim = hidden_size * (2 if bidirectional else 1)
        self.fc = nn.Linear(lstm_out_dim, num_classes)

    def forward(self, x):
        B, C, T, H, W = x.shape
        x = x.permute(0, 2, 1, 3, 4)
        feats = []
        for t in range(T):
            f = self.cnn(x[:, t])
            f = f.view(B, -1)
            feats.append(f)
        feats = torch.stack(feats, dim=1)
        lstm_out, _ = self.lstm(feats)
        last_out = lstm_out[:, -1, :]
        return self.fc(last_out)

class PushbulletAlert:
    def __init__(self, api_key, manual_location=None):
        self.api_key = api_key
        self.base_url = "https://api.pushbullet.com/v2/pushes"
        self.headers = {
            "Access-Token": api_key,
            "Content-Type": "application/json"
        }
        self.sent_alerts = {}
        self.location_service = LocationService(manual_location=manual_location)
        
        # Test location service on initialization
        print("Testing location service...")
        location_info = self.location_service.get_current_location()
        if location_info.get('success'):
            print(f"📍 Location service working: {location_info['address']}")
        else:
            print("⚠️ Location service has issues, but alerts will still work")

    def send_alert(self, event_type, confidence, video_path=None):
        # Update requests to suppress insecure warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Get current location
        location_info = self.location_service.get_current_location()
        network_info = self.location_service.get_network_info()
        
        # Create unique key to prevent duplicate alerts for same event type within 10 minutes
        event_key = f"{event_type}_{int(time.time() // 600)}"
        
        if event_key in self.sent_alerts:
            print(f"Alert already sent for {event_type} in current time window, skipping duplicate")
            return False
        
        title = f"🚨 SECURITY ALERT: {event_type.upper()} DETECTED"
        
        # Build detailed message
        if location_info.get('success'):
            location_msg = f"📍 {location_info['address']}\n🗺️ {location_info['map_url']}"
            if location_info.get('coordinates'):
                location_msg += f"\n📡 Coordinates: {location_info['coordinates']}"
        else:
            location_msg = f"📍 {location_info['address']}"
        
        # Add network information
        network_msg = f"💻 {network_info['hostname']} ({network_info['platform']})"
        
        message = (
            f"🚨 Event: {event_type}\n"
            f"📊 Confidence: {confidence:.2%}\n"
            f"🕐 Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{location_msg}\n"
            f"{network_msg}\n"
            f"🌐 Public IP: {network_info['public_ip']}"
        )
        
        data = {
            "type": "note",
            "title": title,
            "body": message
        }
        
        try:
            response = requests.post(self.base_url, headers=self.headers, data=json.dumps(data), timeout=15, verify=False)
            if response.status_code == 200:
                print(f"✅ Alert sent successfully for {event_type}")
                print(f"📍 Location: {location_info.get('address', 'Unknown')}")
                if location_info.get('method'):
                    print(f"🔧 Method: {location_info['method']}")
                
                self.sent_alerts[event_key] = {
                    'time': time.time(),
                    'event': event_type,
                    'location': location_info
                }
                return True
            else:
                print(f"❌ Failed to send alert. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Network Connection Error: Could not connect to Pushbullet servers.")
            return False
        except Exception as e:
            print(f"❌ Error sending alert: {str(e)}")
            return False

class YOLOv8Detector:
    def __init__(self, model_path='yolov8s.pt', conf_threshold=0.5):
        self.model = YOLO(model_path)
        self.conf_threshold = conf_threshold
        print(f"YOLOv8 model loaded: {model_path}")
    
    def detect(self, frame):
        results = self.model(frame, conf=self.conf_threshold, verbose=False)
        annotated_frame = results[0].plot() if len(results) > 0 else frame.copy()
        return annotated_frame, results

class VideoPredictor:
    def __init__(self, model_path, config_path, pushbullet_api_key, output_dir="detected_events"):
        self.cfg = yaml.safe_load(open(config_path))
        classes_file_path = self.cfg["classes_file"]
        if not os.path.exists(classes_file_path):
            raise FileNotFoundError(f"Classes file not found: {classes_file_path}")
        classes_data = yaml.safe_load(open(classes_file_path))
        
        # The configured model checkpoint is trained on 4 classes:
        # [Explosion, Fighting, RoadAccident, Robbery]
        # We enforce this to match the checkpoint weights exactly.
        self.classes = ["Explosion", "Fighting", "RoadAccident", "Robbery"]
        print(f"✅ AI ENGINE: Using 4-class enforcement: {self.classes}")
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"Using device: {self.device}")
        self.model = VideoClassifier(
            num_classes=4, # Hardcoded to match checkpoint
            backbone=self.cfg["backbone"],
            hidden_size=self.cfg["hidden_size"],
            num_lstm_layers=self.cfg["num_lstm_layers"],
            bidirectional=self.cfg["bidirectional"],
            dropout=self.cfg["dropout"],
            freeze_backbone=self.cfg["freeze_backbone"]
        ).to(self.device)
        
        # Load state dict with safety check
        try:
            checkpoint = torch.load(model_path, map_location=self.device, weights_only=True)
            self.model.load_state_dict(checkpoint)
        except Exception as e:
            print(f"⚠️ Warning loading weights: {e}")
            # Try to load anyway or handle mismatch
            pass
            
        self.model.eval()
        print("Model loaded successfully!")
        self.transform = transforms.Compose([
            transforms.Resize(tuple(self.cfg["resize_hw"])),
            transforms.ToTensor(),
            transforms.ConvertImageDtype(torch.float32),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
        self.expected_len = self.cfg["clip_frames"]
        
        # Check for manual location override in config
        manual_loc = self.cfg.get("node_location")
        self.alert_system = PushbulletAlert(pushbullet_api_key, manual_location=manual_loc)
        
        self.detector = YOLOv8Detector()
        self.alert_threshold = 0.7
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.video_writer = None
        self.is_recording = False
        self.recording_start_time = None
        self.recording_duration = 30
        self.current_event = None

    def extract_frames(self, video_path, num_frames=None):
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        frames = []
        if num_frames is None:
            num_frames = self.cfg["clip_frames"]
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            cap.release()
            raise ValueError("Video has no frames or cannot be read")
        frame_indices = []
        current_frame = 0
        while len(frame_indices) < num_frames and current_frame < total_frames:
            frame_indices.append(current_frame)
            current_frame += self.cfg.get("frame_stride", 1)
        for i, frame_idx in enumerate(frame_indices):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(frame))
        cap.release()
        if len(frames) == 0:
            raise ValueError("No frames were extracted from the video")
        if len(frames) < self.expected_len:
            frames = frames + [frames[-1]] * (self.expected_len - len(frames))
        elif len(frames) > self.expected_len:
            frames = frames[:self.expected_len]      
        return frames

    def preprocess_frames(self, frames):
        imgs = []
        for frame in frames:
            img = self.transform(frame)
            imgs.append(img)
        clip = torch.stack(imgs, dim=0)
        clip = clip.permute(1, 0, 2, 3)
        clip = clip.unsqueeze(0)
        return clip.to(self.device)
    
    def start_recording(self, frame, fps, width, height, event_type, confidence):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(self.output_dir, f"{event_type}_{timestamp}.mp4")
        
        # 'mp4v' is much more reliable on Windows systems without openh264
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        
        self.video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        
        if not self.video_writer.isOpened():
            print(f"❌ CRITICAL: Could not open VideoWriter for {output_path}")
            self.video_writer = None
            self.is_recording = False
            return

        self.is_recording = True
        self.recording_start_time = time.time()
        print(f"Started recording: {output_path}")
        annotated_frame = frame.copy()
        cv2.putText(annotated_frame, f"Event: {event_type} ({confidence:.2%})", 
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        cv2.putText(annotated_frame, f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                    (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        self.video_writer.write(annotated_frame)
    
    def stop_recording(self):
        if self.video_writer is not None:
            self.video_writer.release()
            self.video_writer = None
        self.is_recording = False
        self.recording_start_time = None
        print("Stopped recording")
    
    def process_video_realtime(self, video_path):
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")
        fps = int(cap.get(cv2.CAP_PROP_FPS))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        classification_buffer = []
        frame_count = 0
        classification_interval = fps // 2
        print(f"Processing video: {os.path.basename(video_path)}")
        print(f"Video properties: {width}x{height}, {fps} FPS")
        final_prediction = None
        final_confidence = 0.0
        final_probabilities = None
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_count += 1
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            annotated_frame, detection_results = self.detector.detect(rgb_frame)
            
            if len(classification_buffer) < self.expected_len:
                pil_frame = Image.fromarray(rgb_frame)
                classification_buffer.append(pil_frame)
            
            event_detected = False
            if frame_count % classification_interval == 0 and len(classification_buffer) >= self.expected_len:
                clip = self.preprocess_frames(classification_buffer)
                with torch.no_grad():
                    outputs = self.model(clip)
                    probabilities = torch.softmax(outputs, dim=1)
                    confidence, predicted = torch.max(probabilities, 1)
                predicted_class = self.classes[predicted.item()]
                confidence_value = confidence.item()
                final_prediction = predicted_class
                final_confidence = confidence_value
                final_probabilities = probabilities.cpu().numpy()
                
                if confidence_value > self.alert_threshold:
                    event_detected = True
                    if self.current_event != predicted_class:
                        print(f"🚨 Event detected: {predicted_class} ({confidence_value:.2%})")
                        # Send alert with current location
                        self.alert_system.send_alert(predicted_class, confidence_value)
                        if not self.is_recording:
                            self.start_recording(annotated_frame, fps, width, height, 
                                                 predicted_class, confidence_value)
                        self.current_event = predicted_class
            
            if self.is_recording:
                self.video_writer.write(annotated_frame)
                if time.time() - self.recording_start_time > self.recording_duration:
                    self.stop_recording()
                    self.current_event = None
            
            if len(classification_buffer) >= self.expected_len:
                classification_buffer.pop(0)
        
        cap.release()
        if self.is_recording:
            self.stop_recording()
        if final_prediction is not None:
            self.display_prediction(video_path, final_prediction, final_confidence, final_probabilities)
    
    def predict_video(self, video_path, num_samples=8):
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Could not open video: {video_path}")
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            frames_per_sample = self.cfg.get("clip_frames", 16)
            
            # If the video is too short, fall back to simple extraction
            if total_frames <= frames_per_sample:
                cap.release()
                frames = self.extract_frames(video_path, num_frames=frames_per_sample)
                clip = self.preprocess_frames(frames)
                with torch.no_grad():
                    outputs = self.model(clip)
                    probs = torch.softmax(outputs, dim=1)
                    conf, pred = torch.max(probs, 1)
                best_class = self.classes[pred.item()]
                best_conf = conf.item()
                best_probs = probs.cpu().numpy()
            else:
                # Sample equally spaced starting points
                step = max(1, (total_frames - frames_per_sample) // num_samples)
                start_indices = [i * step for i in range(num_samples)]
                
                best_class = None
                best_conf = -1.0
                best_probs = None
                
                for start_idx in start_indices:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, start_idx)
                    frames = []
                    for _ in range(frames_per_sample):
                        ret, frame = cap.read()
                        if not ret: break
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        frames.append(Image.fromarray(frame))
                    
                    if len(frames) == 0:
                        continue
                        
                    # Pad if necessary
                    if len(frames) < frames_per_sample:
                        frames = frames + [frames[-1]] * (frames_per_sample - len(frames))
                        
                    clip = self.preprocess_frames(frames)
                    with torch.no_grad():
                        outputs = self.model(clip)
                        probs = torch.softmax(outputs, dim=1)
                        conf, pred = torch.max(probs, 1)
                        
                    c_class = self.classes[pred.item()]
                    c_conf = conf.item()
                    
                    if c_conf > best_conf:
                        best_conf = c_conf
                        best_class = c_class
                        best_probs = probs.cpu().numpy()
                cap.release()
            
            if best_class is None:
                raise ValueError("No frames could be extracted")
                
            if best_conf > self.alert_threshold:
                self.alert_system.send_alert(best_class, best_conf)
                
            return best_class, best_conf, best_probs
        except Exception as e:
            return f"Error: {str(e)}", 0.0, None
    
    def display_prediction(self, video_path, prediction, confidence, probabilities=None):
        print("\n" + "="*50)
        print(f"PREDICTION RESULTS")
        print("="*50)
        print(f"Video: {os.path.basename(video_path)}")
        print(f"Predicted Class: {prediction}")
        print(f"Confidence: {confidence:.4f}")
        if probabilities is not None and not isinstance(prediction, str):
            print("\nTop Predictions:")
            print("-" * 30)
            probs = probabilities[0]
            top_indices = np.argsort(probs)[-5:][::-1]
            for i in top_indices:
                print(f"  {self.classes[i]:<15}: {probs[i]:.4f}")
        print("="*50)
    
    def monitor_folder(self, folder_path, check_interval=10):
        print(f"Monitoring folder: {folder_path}")
        processed_files = set()
        while True:
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv']
            video_files = []
            for ext in video_extensions:
                video_files.extend(Path(folder_path).glob(f"*{ext}"))
                video_files.extend(Path(folder_path).glob(f"*{ext.upper()}"))
            for video_file in video_files:
                if str(video_file) not in processed_files:
                    print(f"Processing new video: {video_file.name}")
                    self.process_video_realtime(str(video_file))
                    processed_files.add(str(video_file))
            time.sleep(check_interval)

def main():
    try:
        predictor = VideoPredictor(
            model_path="runs_ucf/best_model.pth",
            config_path="config.yaml",
            pushbullet_api_key=os.getenv("PUSHBULLET_API_KEY", "")
        )
        video_path = r"dataset/Fighting/Fighting027_x264.mp4"
        if os.path.exists(video_path):
            predictor.process_video_realtime(video_path)
        else:
            print(f"Video file not found: {video_path}")
            print("Please check the path and try again.")
            
            # Test with a sample video or show location test
            print("\nTesting location service independently...")
            location_service = LocationService()
            location_info = location_service.get_current_location()
            if location_info.get('success'):
                print(f" Location test successful:")
                print(f" Address: {location_info['address']}")
                print(f" Map URL: {location_info['map_url']}")
                print(f" Method: {location_info['method']}")
            else:
                print(f"Location test failed: {location_info['address']}")
                
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()