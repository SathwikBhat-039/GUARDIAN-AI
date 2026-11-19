import torch
import torch.nn as nn
from tqdm import tqdm
import yaml
from multiprocessing import freeze_support  

from dataset_clip import get_dataloaders
from model import VideoClassifier

def main():
   
    cfg = yaml.safe_load(open("config.yaml"))

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

   
    _, val_loader = get_dataloaders(
        batch_size=cfg["batch_size"],
        clip_len=cfg["clip_frames"],
        num_workers=cfg["num_workers"],
        resize=tuple(cfg["resize_hw"])
    )

   
    model = VideoClassifier(
        num_classes=len(yaml.safe_load(open(cfg["classes_file"]))["classes"]),
        backbone=cfg["backbone"],
        hidden_size=cfg["hidden_size"],
        num_lstm_layers=cfg["num_lstm_layers"],
        bidirectional=cfg["bidirectional"],
        dropout=cfg["dropout"]
    ).to(device)

    checkpoint = torch.load("runs_ucf/best_model.pth", map_location=device)
    model.load_state_dict(checkpoint)
    model.eval()

  
    correct, total = 0, 0
    criterion = nn.CrossEntropyLoss()
    val_loss = 0.0

    with torch.no_grad():
        for clips, labels in tqdm(val_loader, desc="Testing"):
            clips, labels = clips.to(device), labels.to(device)
            outputs = model(clips)
            loss = criterion(outputs, labels)
            val_loss += loss.item()

            _, preds = torch.max(outputs, 1)
            correct += (preds == labels).sum().item()
            total += labels.size(0)

    accuracy = 100 * correct / total
    avg_loss = val_loss / len(val_loader)

    print(f"✅ Test Accuracy: {accuracy:.2f}% | Avg Loss: {avg_loss:.4f}")

if __name__ == '__main__':
    freeze_support()  
    main()