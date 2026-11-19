from sklearn.metrics import classification_report, confusion_matrix
import seaborn as sns
import matplotlib.pyplot as plt
import numpy as np
import torch
import torch.nn as nn
from tqdm import tqdm
import yaml
from multiprocessing import freeze_support
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from dataset_clip import get_dataloaders
    from model import VideoClassifier
    print("✅ Successfully imported modules")
except ImportError as e:
    print(f" Import error: {e}")
    print("Current working directory:", os.getcwd())
    print("Files in directory:", os.listdir('.'))
    sys.exit(1)

def main():
    print(" Starting evaluation script...")
    
    
    try:
        with open("config.yaml", "r") as f:
            cfg = yaml.safe_load(f)
        print(" Config loaded successfully")
        print(f"Config: {cfg}")
    except FileNotFoundError:
        print(" config.yaml not found!")
        print("Current files:", os.listdir('.'))
        return
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"📱 Using device: {device}")

   
    try:
        classes_data = yaml.safe_load(open(cfg["classes_file"]))
        class_names = classes_data["classes"]
        print(f" Class names: {class_names}")
        print(f" Number of classes: {len(class_names)}")
    except Exception as e:
        print(f" Error loading classes file: {e}")
        return

   
    try:
        print(" Loading data...")
        _, val_loader = get_dataloaders(
            batch_size=cfg["batch_size"],
            clip_len=cfg["clip_frames"],
            num_workers=0,  
            resize=tuple(cfg["resize_hw"])
        )
        print(f" Data loaded. Validation batches: {len(val_loader)}")
    except Exception as e:
        print(f"Error loading data: {e}")
        return

  
    try:
        print(" Loading model...")
        model = VideoClassifier(
            num_classes=len(class_names),
            backbone=cfg["backbone"],
            hidden_size=cfg["hidden_size"],
            num_lstm_layers=cfg["num_lstm_layers"],
            bidirectional=cfg["bidirectional"],
            dropout=cfg["dropout"]
        ).to(device)

        model_path = "runs_ucf/best_model.pth"
        if not os.path.exists(model_path):
            print(f"Model file not found: {model_path}")
            print("Available files in runs_ucf:", os.listdir('runs_ucf') if os.path.exists('runs_ucf') else "Directory doesn't exist")
            return

        checkpoint = torch.load(model_path, map_location=device)
        model.load_state_dict(checkpoint)
        model.eval()
        print("Model loaded successfully")
    except Exception as e:
        print(f" Error loading model: {e}")
        return

    
    print("🔮 Making predictions...")
    all_preds = []
    all_labels = []
    
    try:
        with torch.no_grad():
            for clips, labels in tqdm(val_loader, desc="Testing"):
                clips, labels = clips.to(device), labels.to(device)
                outputs = model(clips)
                
                _, preds = torch.max(outputs, 1)
                
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())

        print(f" Predictions complete. Samples: {len(all_preds)}")
    except Exception as e:
        print(f" Error during prediction: {e}")
        return

    y_pred = np.array(all_preds)
    y_true = np.array(all_labels)

    print(f" Data shapes - True: {y_true.shape}, Pred: {y_pred.shape}")
    print(f" Unique true labels: {np.unique(y_true)}")
    print(f" Unique predicted labels: {np.unique(y_pred)}")

    
    print("\n" + "="*50)
    print(" CLASSIFICATION REPORT:")
    print("="*50)
    
    try:
        report = classification_report(y_true, y_pred, target_names=class_names)
        print(report)
    except Exception as e:
        print(f" Error in classification report: {e}")

    
    try:
        cm = confusion_matrix(y_true, y_pred)
        print(f" Confusion matrix shape: {cm.shape}")
        
        plt.figure(figsize=(10, 8))
        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                    xticklabels=class_names,
                    yticklabels=class_names)
        plt.title("Confusion Matrix")
        plt.ylabel('True Label')
        plt.xlabel('Predicted Label')
        plt.xticks(rotation=45)
        plt.yticks(rotation=0)
        plt.tight_layout()
        plt.savefig('confusion_matrix.png')
        print(" Confusion matrix saved as 'confusion_matrix.png'")
        plt.show()
    except Exception as e:
        print(f"Error creating confusion matrix: {e}")

    
    try:
        accuracy = 100 * np.sum(y_pred == y_true) / len(y_true)
        print(f" Overall Accuracy: {accuracy:.2f}%")
    except Exception as e:
        print(f" Error calculating accuracy: {e}")

    print(" Evaluation completed!")

if __name__ == '__main__':
    freeze_support()
    print(" Python script started")
    main()