import os, random, yaml
from pathlib import Path
from PIL import Image
import torch
from torch.utils.data import Dataset, DataLoader
import torchvision.transforms as T

class ClipFolderDataset(Dataset):
    def __init__(self, clips_root, split="train", classes_file=None,
                 val_ratio=0.15, seed=42, expected_len=16, resize=(224,224)):
        self.root = Path(clips_root)

        if classes_file is None:
            classes_file = Path(clips_root) / "classes.yaml"

        meta = yaml.safe_load(open(classes_file))
        all_classes = meta["classes"]

        self.classes = [c for c in all_classes if c in ["roadaccident", "fighting", "robbery", "explosion"]]
        self.class_to_idx = {cls: i for i, cls in enumerate(self.classes)}

        self.expected_len = expected_len
        self.transform = T.Compose([
            T.Resize(resize),
            T.ToTensor(),
            T.ConvertImageDtype(torch.float32),
            T.Normalize(mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]),
        ])

        all_clips = []
        for cls in self.classes:
            for clip_dir in (self.root/cls).glob("*"):
                if not clip_dir.is_dir():
                    continue
                frames = sorted(list(clip_dir.glob("frame_*.jpg")))
                if len(frames) >= expected_len:
                    all_clips.append((clip_dir, self.class_to_idx[cls]))

        random.seed(seed)
        random.shuffle(all_clips)
        n_val = int(len(all_clips) * val_ratio)
        self.val = all_clips[:n_val]
        self.train = all_clips[n_val:]

        self.split = split
        self.samples = self.train if split == "train" else self.val
        print(f"{split}: {len(self.samples)} clips | classes={len(self.classes)} -> {self.classes}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        clip_dir, label = self.samples[idx]
        frames = sorted(list(clip_dir.glob("frame_*.jpg")))

        if len(frames) >= self.expected_len:
            start = random.randint(0, len(frames) - self.expected_len)
            frames = frames[start:start+self.expected_len]
        else:
            frames = frames + [frames[-1]] * (self.expected_len - len(frames))

        imgs = []
        for p in frames:
            img = Image.open(p).convert("RGB")
            imgs.append(self.transform(img))

        clip = torch.stack(imgs, dim=0)
        clip = clip.permute(1, 0, 2, 3)

        return clip, torch.tensor(label, dtype=torch.long)

def get_dataloaders(batch_size=8, clip_len=16, num_workers=4, resize=(224,224)):
    cfg = yaml.safe_load(open("config.yaml"))
    clips_root = cfg["clips_root"]
    classes_file = cfg.get("classes_file", None)
    val_ratio = cfg.get("val_ratio", 0.15)
    seed = cfg.get("seed", 42)

    train_dataset = ClipFolderDataset(
        clips_root=clips_root,
        split="train",
        classes_file=classes_file,
        val_ratio=val_ratio,
        seed=seed,
        expected_len=clip_len,
        resize=resize
    )
    val_dataset = ClipFolderDataset(
        clips_root=clips_root,
        split="val",
        classes_file=classes_file,
        val_ratio=val_ratio,
        seed=seed,
        expected_len=clip_len,
        resize=resize
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=True
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=True
    )

    return train_loader, val_loader