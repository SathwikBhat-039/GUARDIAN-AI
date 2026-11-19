import os, yaml, torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from tqdm import tqdm
from dataset_clip import get_dataloaders
import torchvision.models as models

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

def train_model(cfg, device):
    train_loader, val_loader = get_dataloaders(
        batch_size=cfg["batch_size"],
        clip_len=cfg["clip_frames"],
        num_workers=cfg["num_workers"],
        resize=tuple(cfg["resize_hw"])
    )

    meta = yaml.safe_load(open(cfg["classes_file"]))
    classes = meta["classes"]
    num_classes = len(classes)

    model = VideoClassifier(
        num_classes=num_classes,
        backbone=cfg["backbone"],
        hidden_size=cfg["hidden_size"],
        num_lstm_layers=cfg["num_lstm_layers"],
        bidirectional=cfg["bidirectional"],
        dropout=cfg["dropout"],
        freeze_backbone=cfg["freeze_backbone"]
    ).to(device)

    criterion = nn.CrossEntropyLoss(label_smoothing=cfg.get("label_smoothing", 0.0))
    optimizer = optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])

    best_val_acc = 0.0
    patience_counter = 0

    for epoch in range(cfg["epochs"]):
        print(f"\nEpoch {epoch+1}/{cfg['epochs']}")

        model.train()
        total_loss, correct, total = 0, 0, 0
        for clips, labels in tqdm(train_loader, desc=f"Train {epoch+1}"):
            clips, labels = clips.to(device), labels.to(device)

            optimizer.zero_grad()
            outputs = model(clips)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            correct += (outputs.argmax(1) == labels).sum().item()
            total += labels.size(0)

        train_acc = correct / total
        print(f"Train Loss: {total_loss/len(train_loader):.4f}, Acc: {train_acc:.4f}")

        model.eval()
        val_correct, val_total, val_loss = 0, 0, 0
        with torch.no_grad():
            for clips, labels in tqdm(val_loader, desc=f"Val {epoch+1}"):
                clips, labels = clips.to(device), labels.to(device)
                outputs = model(clips)
                loss = criterion(outputs, labels)

                val_loss += loss.item()
                val_correct += (outputs.argmax(1) == labels).sum().item()
                val_total += labels.size(0)

        val_acc = val_correct / val_total
        print(f"Val Loss: {val_loss/len(val_loader):.4f}, Acc: {val_acc:.4f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            patience_counter = 0
            os.makedirs(cfg["out_dir"], exist_ok=True)
            ckpt_path = os.path.join(cfg["out_dir"], f"best_model.pth")
            torch.save(model.state_dict(), ckpt_path)
            print(f"Saved best model at {ckpt_path}")
        else:
            patience_counter += 1
            if patience_counter >= cfg["early_stop_patience"]:
                print("Early stopping triggered")
                break

if __name__ == "__main__":
    cfg = yaml.safe_load(open("config.yaml"))
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Using device:", device)
    train_model(cfg, device)