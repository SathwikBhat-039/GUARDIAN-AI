import os, cv2, math, shutil, yaml
from pathlib import Path
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

def list_videos(root):
    classes, items = [], []
    for c in sorted(os.listdir(root)):
        p = os.path.join(root, c)
        if not os.path.isdir(p): continue
        classes.append(c)
        for f in os.listdir(p):
            if f.lower().endswith((".mp4",".avi",".mov",".mkv",".mpg",".mpeg",".wmv")):
                items.append((c, os.path.join(p,f)))
    return classes, items

def extract_clips(args):
    cls, video_path, out_class_dir, cfg = args
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return 0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total < cfg["min_frames_per_video"]:
        cap.release()
        return 0

    needed = cfg["clip_frames"] * cfg["frame_stride"]
    n_clips = max(0, math.floor((total - needed) / (cfg["clip_frames"])) + 1)

    if cfg["clips_per_video_limit"] > 0:
        n_clips = min(n_clips, cfg["clips_per_video_limit"])

    h, w = cfg["resize_hw"]
    base = Path(video_path).stem

    saved = 0
    for clip_idx in range(n_clips):
        start_frame = clip_idx * cfg["clip_frames"]
        clip_dir = Path(out_class_dir) / f"{base}_clip{clip_idx:04d}"
        clip_dir.mkdir(parents=True, exist_ok=True)

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        frame_count, saved_this = 0, 0
        while frame_count < cfg["clip_frames"]:
            ret, frame = cap.read()
            if not ret: break
            if (frame_count * cfg["frame_stride"]) >= total: break
            frame = cv2.resize(frame, (w, h))
            cv2.imwrite(str(clip_dir / f"frame_{frame_count:03d}.jpg"), frame)
            frame_count += 1
            saved_this += 1

        if saved_this == cfg["clip_frames"]:
            saved += 1
        else:
            shutil.rmtree(clip_dir, ignore_errors=True)

    cap.release()
    return saved

def main():
    cfg = yaml.safe_load(open("config.yaml"))
    raw_root, clips_root = cfg["raw_dataset_dir"], cfg["clips_root"]
    Path(clips_root).mkdir(parents=True, exist_ok=True)

    classes, items = list_videos(raw_root)
    print(f"Found {len(classes)} classes, {len(items)} videos.")

    class_map = {c:i for i,c in enumerate(classes)}
    yaml.safe_dump({"classes": classes, "class_to_idx": class_map},
                   open(Path(clips_root)/"classes.yaml","w"))

    args = [(cls, vp, Path(clips_root)/cls, cfg) for cls, vp in items]
    for c in classes:
        Path(clips_root, c).mkdir(parents=True, exist_ok=True)

    with Pool(cpu_count()) as pool:
        results = list(tqdm(pool.imap(extract_clips, args), total=len(args), desc="Processing"))

    print(f"✅ Done. Saved {sum(results)} clips in '{clips_root}'")

if __name__ == "__main__":
    main()
