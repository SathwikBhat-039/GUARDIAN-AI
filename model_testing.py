import torch
import cv2
import numpy as np
from model import VideoClassifier
from torchvision import transforms

transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224, 224)),
    transforms.ToTensor()
])

class_names = ["Fighting", "RoadAccident", "Robbery", "Explosion"]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = VideoClassifier(num_classes=4).to(device)
checkpoint = torch.load("runs_ucf/best_model.pth", map_location=device)
model.load_state_dict(checkpoint)
model.eval()

def preprocess_clip(frames):
    processed = []
    for frame in frames:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = transform(frame)
        processed.append(frame)
    clip = torch.stack(processed)
    clip = clip.unsqueeze(0)
    return clip

def predict_video(video_path):
    cap = cv2.VideoCapture(video_path)
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()

    if len(frames) < 16:
        indices = np.linspace(0, len(frames)-1, 16).astype(int)
        frames = [frames[i] for i in indices]
    else:
        indices = np.linspace(0, len(frames)-1, 16).astype(int)
        frames = [frames[i] for i in indices]

    clip = preprocess_clip(frames).to(device)

    with torch.no_grad():
        outputs = model(clip)
        _, predicted = torch.max(outputs, 1)

    label = class_names[predicted.item()]
    return label

if __name__ == "__main__":
    video_path = "test_videos/sample.mp4"
    result = predict_video(video_path)
    print(f"Predicted Class: {result}")