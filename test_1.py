import torch
import os
import torch.nn as nn
import cv2
import numpy as np
import torchvision.transforms as transforms
from model import VideoClassifier  


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


num_classes = 4 
model = VideoClassifier(num_classes=num_classes).to(device)

checkpoint = torch.load(
    os.path.join("runs_ucf", "best_model.pth"),
    map_location=device
)
if "model_state_dict" in checkpoint:
    model.load_state_dict(checkpoint["model_state_dict"])
else:
    model.load_state_dict(checkpoint) 
model.eval()


label_map = {
    0: "Fighting",
    1: "RoadAccident",
    2: "Robbery",
    3: "Explosion"
}


transform = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((224, 224)),
    transforms.ToTensor()
])


def predict_video(video_path, clip_len=16):
    cap = cv2.VideoCapture(video_path)
    frames = []
    predictions = []

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = transform(frame)  
        frames.append(frame)

        if len(frames) == clip_len:
            clip = torch.stack(frames, dim=0)    
            clip = clip.unsqueeze(0).to(device)   

            with torch.no_grad():
                outputs = model(clip)
                _, pred = torch.max(outputs, 1)
                predictions.append(pred.item())

            frames = []  

    cap.release()

    if len(predictions) == 0:
        return "Not enough frames for a clip"

    final_pred = max(set(predictions), key=predictions.count)
    return label_map[final_pred]



if __name__ == "__main__":
    video_path = os.path.join("dataset", "Fighting", "Fighting003_x264.mp4")
    result = predict_video(video_path)
    print("Final Prediction:", result)
