import argparse
import queue
import threading
import time
from collections import defaultdict

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from sort.sort import Sort
from util import get_car, read_license_plate

import csv
import datetime
import os

# Determine best device (Apple Silicon MPS, CUDA, or CPU)
if torch.backends.mps.is_available():
    DEVICE = 'mps'
elif torch.cuda.is_available():
    DEVICE = 'cuda'
else:
    DEVICE = 'cpu'


class RealtimeANPR:
    def __init__(self, video_source, plate_model_path='./models/license_plate_detector.pt',
                 coco_model_path='yolov8n.pt', output_csv='realtime_log.csv'):
        print(f"[*] Initializing Real-time ANPR on device: {DEVICE}")
        
        # Load models
        self.coco_model = YOLO(coco_model_path)
        self.license_plate_detector = YOLO(plate_model_path)
        
        self.coco_model.to(DEVICE)
        self.license_plate_detector.to(DEVICE)
        
        # Tracking
        self.mot_tracker = Sort(max_age=15, min_hits=2, iou_threshold=0.3)
        self.vehicles_classes = [2, 3, 5, 7]  # car, motorcycle, bus, truck

        # Plate cache: car_id -> {'text': str, 'score': float, 'crop': np.ndarray, 'last_seen': float}
        self.plate_cache = defaultdict(dict)

        # CSV Logging Setup
        self.output_csv = output_csv
        self.csv_lock = threading.Lock()
        self._init_csv()
        
        # Background OCR worker queue
        self.ocr_queue = queue.Queue(maxsize=16)
        self.running = True
        self.ocr_thread = threading.Thread(target=self._ocr_worker, daemon=True)
        self.ocr_thread.start()

        self.video_source = video_source

    def _init_csv(self):
        """Initialize CSV log file with header if not exists."""
        if self.output_csv:
            file_exists = os.path.isfile(self.output_csv)
            with open(self.output_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists or os.stat(self.output_csv).st_size == 0:
                    writer.writerow([
                        'timestamp',
                        'frame_nmr',
                        'car_id',
                        'license_plate_number',
                        'confidence_score',
                        'car_bbox',
                        'plate_bbox'
                    ])
            print(f"[*] Logging real-time detections to: {self.output_csv}")

    def _log_detection_to_csv(self, frame_nmr, car_id, plate_text, score, car_bbox, plate_bbox):
        """Thread-safe write to real-time CSV log."""
        if not self.output_csv:
            return
        with self.csv_lock:
            with open(self.output_csv, 'a', newline='') as f:
                writer = csv.writer(f)
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                car_bbox_str = f"[{car_bbox[0]} {car_bbox[1]} {car_bbox[2]} {car_bbox[3]}]" if car_bbox else ""
                plate_bbox_str = f"[{plate_bbox[0]} {plate_bbox[1]} {plate_bbox[2]} {plate_bbox[3]}]" if plate_bbox else ""
                writer.writerow([
                    now_str,
                    frame_nmr,
                    car_id,
                    plate_text,
                    f"{score:.4f}",
                    car_bbox_str,
                    plate_bbox_str
                ])

    def _ocr_worker(self):
        """Asynchronous worker to process OCR without blocking video playback."""
        while self.running:
            try:
                task = self.ocr_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            car_id, plate_crop, frame_nmr, car_bbox, plate_bbox = task
            try:
                # Preprocess crop
                plate_gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
                _, plate_thresh = cv2.threshold(plate_gray, 64, 255, cv2.THRESH_BINARY_INV)

                text, score = read_license_plate(plate_thresh)
                if text is None:
                    text, score = read_license_plate(plate_gray)

                if text is not None:
                    current_best_score = self.plate_cache[car_id].get('score', 0.0)
                    if score > current_best_score or self.plate_cache[car_id].get('text') is None:
                        # Resize crop for thumbnail display
                        h, w = plate_crop.shape[:2]
                        thumb_w = max(1, int(w * 80 / max(h, 1)))
                        thumb = cv2.resize(plate_crop, (thumb_w, 80))
                        
                        self.plate_cache[car_id] = {
                            'text': text,
                            'score': score,
                            'crop': thumb,
                            'last_seen': time.time()
                        }
                        # Log real-time detection event to CSV
                        self._log_detection_to_csv(frame_nmr, car_id, text, score, car_bbox, plate_bbox)
            except Exception as e:
                pass
            finally:
                self.ocr_queue.task_done()

    def run(self):
        # Open video source (can be int for webcam, or str for file/rtsp)
        try:
            source = int(self.video_source)
            cap = cv2.VideoCapture(source)
            if not cap.isOpened():
                cap = cv2.VideoCapture(source, cv2.CAP_AVFOUNDATION)
        except ValueError:
            source = self.video_source
            cap = cv2.VideoCapture(source)

        if not cap.isOpened():
            print(f"[!] Error: Could not open video source '{self.video_source}'")
            print("[!] Tip: On macOS, make sure Camera permission is granted in System Settings -> Privacy & Security -> Camera.")
            return

        window_name = "Real-Time Automatic Number Plate Recognition"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 1280, 720)

        fps_prev_time = time.time()
        fps = 0.0
        frame_nmr = 0

        print("[*] Starting real-time stream. Press 'q' or 'ESC' to exit.")

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("[*] End of video stream.")
                break

            frame_nmr += 1
            h, w, _ = frame.shape

            # 1. Vehicle Detection
            coco_results = self.coco_model(frame, verbose=False, device=DEVICE)[0]
            detections = []
            for det in coco_results.boxes.data.tolist():
                x1, y1, x2, y2, score, class_id = det
                if int(class_id) in self.vehicles_classes and score > 0.35:
                    detections.append([x1, y1, x2, y2, score])

            # 2. Track Vehicles
            if len(detections) > 0:
                track_ids = self.mot_tracker.update(np.asarray(detections))
            else:
                track_ids = self.mot_tracker.update()

            # 3. Plate Detection
            plate_results = self.license_plate_detector(frame, verbose=False, device=DEVICE)[0]
            
            for plate_det in plate_results.boxes.data.tolist():
                x1, y1, x2, y2, plate_score, class_id = plate_det
                if plate_score < 0.3:
                    continue

                # Associate plate to vehicle
                xcar1, ycar1, xcar2, ycar2, car_id = get_car(plate_det, track_ids)

                if car_id != -1:
                    car_id = int(car_id)
                    
                    # Draw plate box
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)

                    # Extract crop and submit to async OCR if needed
                    crop = frame[max(0, int(y1)):min(h, int(y2)), max(0, int(x1)):min(w, int(x2))]
                    if crop.size > 0 and not self.ocr_queue.full():
                        cached = self.plate_cache.get(car_id)
                        # Re-run OCR if not recognized yet or low score
                        if not cached or cached.get('score', 0) < 0.6:
                            try:
                                car_bbox = [int(xcar1), int(ycar1), int(xcar2), int(ycar2)]
                                plate_bbox = [int(x1), int(y1), int(x2), int(y2)]
                                self.ocr_queue.put_nowait((car_id, crop.copy(), frame_nmr, car_bbox, plate_bbox))
                            except queue.Full:
                                pass

            # 4. Draw Vehicle Bounding Boxes and HUD info
            for track in track_ids:
                tx1, ty1, tx2, ty2, car_id = map(int, track[:5])
                
                # Draw vehicle box
                cv2.rectangle(frame, (tx1, ty1), (tx2, ty2), (0, 255, 0), 2)
                
                plate_info = self.plate_cache.get(car_id)
                label = f"Car #{car_id}"
                if plate_info and plate_info.get('text'):
                    label += f" | Plate: {plate_info['text']} ({plate_info['score']:.2f})"

                # Draw label background badge
                (lbl_w, lbl_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
                badge_x1 = max(0, min(w - 10, tx1))
                badge_y1 = max(0, ty1 - lbl_h - 10)
                badge_x2 = min(w, badge_x1 + lbl_w + 10)
                badge_y2 = min(h, badge_y1 + lbl_h + 8)
                cv2.rectangle(frame, (badge_x1, badge_y1), (badge_x2, badge_y2), (0, 180, 0), -1)
                cv2.putText(frame, label, (badge_x1 + 5, min(h - 5, badge_y1 + lbl_h + 3)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                # Overlay plate thumbnail above vehicle if available
                if plate_info and 'crop' in plate_info:
                    try:
                        thumb = plate_info['crop']
                        th, tw = thumb.shape[:2]
                        ov_y1 = max(0, badge_y1 - th - 5)
                        ov_y2 = min(h, ov_y1 + th)
                        ov_x1 = max(0, min(w - 1, tx1))
                        ov_x2 = min(w, ov_x1 + tw)
                        
                        target_h = ov_y2 - ov_y1
                        target_w = ov_x2 - ov_x1
                        if target_h > 0 and target_w > 0:
                            frame[ov_y1:ov_y2, ov_x1:ov_x2] = thumb[:target_h, :target_w]
                    except Exception:
                        pass

            # 5. Compute & Draw Live FPS
            curr_time = time.time()
            fps = 1.0 / (curr_time - fps_prev_time) if curr_time > fps_prev_time else fps
            fps_prev_time = curr_time

            cv2.putText(frame, f"FPS: {fps:.1f} | Device: {DEVICE}", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)

            cv2.imshow(window_name, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break

        self.running = False
        cap.release()
        cv2.destroyAllWindows()
        print("[*] Stream closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-Time Automatic Number Plate Recognition")
    parser.add_argument("--source", type=str, default="0",
                        help="Video source: '0' or webcam index, video file path, or RTSP URL (default: 0)")
    parser.add_argument("--plate-model", type=str, default="./models/license_plate_detector.pt",
                        help="Path to YOLO license plate detector weights")
    parser.add_argument("--coco-model", type=str, default="yolov8n.pt",
                        help="Path to YOLO COCO weights")
    parser.add_argument("--output-csv", type=str, default="realtime_log.csv",
                        help="Path to output CSV log file for real-time detections (default: realtime_log.csv)")
    args = parser.parse_args()

    app = RealtimeANPR(
        video_source=args.source,
        plate_model_path=args.plate_model,
        coco_model_path=args.coco_model,
        output_csv=args.output_csv
    )
    app.run()
