import cv2
import os
from ultralytics import YOLO


def main(video_path, output_path="output_with_event.mp4"):
    # Load YOLOv8s model
    model = YOLO("yolov8s.pt")  # Make sure yolov8s.pt is accessible in your environment

    # Open input video
    cap = cv2.VideoCapture(video_path)

    # Video properties for saving output
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)

    # Define codec and create VideoWriter to save annotated video
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Perform object detection on the frame
        results = model(frame)

        # Draw bounding boxes and labels for each detection
        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = box.conf[0]
                cls = int(box.cls[0])
                label = f"{model.model.names[cls]} {conf:.2f}"
                # Draw rectangle and put label text
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX,
                            0.5, (0, 255, 0), 2)

        # Overlay custom event text with two colors
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.2
        thickness = 3
        x, y = 30, 40 + 30  # position for baseline adjusted by text height

        # Text parts and colors
        text1 = "Event: "
        color1 = (0, 255, 0)  # Green
        cv2.putText(frame, text1, (x, y), font, font_scale, color1, thickness)

        # Measure width of first part so next can start right after
        (text1_width, _), _ = cv2.getTextSize(text1, font, font_scale, thickness)
        
        text2 = "Stealling"
        color2 = (0, 0, 255)  # Red
        cv2.putText(frame, text2, (x + text1_width, y), font, font_scale, color2, thickness)

        # Show annotated frame in window
        cv2.imshow('YOLOv8 Detection', frame)
        # Write frame to output video file
        out.write(frame)

        # Exit on 'q' key press
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Release resources
    cap.release()
    out.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    input_video = os.path.join("dataset", "Stealing", "Stalling.mp4")
    output_video = "output_with_event.mp4"  # Will save here - you can change path if you want
    main(input_video, output_video)
