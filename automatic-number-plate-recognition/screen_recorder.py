import argparse
import collections
import csv
import datetime
import os
import queue
import threading
import time
from collections import defaultdict

import cv2
import mss
import numpy as np
import torch
from ultralytics import YOLO

from sort.sort import Sort
from util import get_car, read_license_plate

# Determine best hardware acceleration device
if torch.backends.mps.is_available():
    DEVICE = 'mps'
elif torch.cuda.is_available():
    DEVICE = 'cuda'
else:
    DEVICE = 'cpu'


class ScreenANPRRecorder:
    def __init__(self, monitor_index=1, output_dir="recordings",
                 pre_buffer_seconds=2.0, post_record_seconds=4.0,
                 min_ocr_score=0.25, show_preview=True,
                 plate_model_path='./models/license_plate_detector.pt',
                 coco_model_path='yolov8n.pt'):
        self.monitor_index = monitor_index
        self.output_dir = output_dir
        self.snapshots_dir = os.path.join(output_dir, "snapshots")
        self.videos_dir = os.path.join(output_dir, "videos")
        os.makedirs(self.snapshots_dir, exist_ok=True)
        os.makedirs(self.videos_dir, exist_ok=True)

        self.pre_buffer_seconds = pre_buffer_seconds
        self.post_record_seconds = post_record_seconds
        self.min_ocr_score = min_ocr_score
        self.show_preview = show_preview

        self.csv_file = os.path.join(output_dir, "screen_detections.csv")
        self.csv_lock = threading.Lock()
        self._init_csv()

        print(f"[*] Initializing Screen ANPR on device: {DEVICE}")
        print(f"[*] Target Monitor: {self.monitor_index}")
        print(f"[*] Recordings directory: {self.output_dir}")

        # Load models
        self.coco_model = YOLO(coco_model_path)
        self.license_plate_detector = YOLO(plate_model_path)
        self.coco_model.to(DEVICE)
        self.license_plate_detector.to(DEVICE)

        # Vehicle tracker & classes
        self.mot_tracker = Sort(max_age=20, min_hits=2, iou_threshold=0.3)
        self.vehicles_classes = [2, 3, 5, 7]  # car, motorcycle, bus, truck

        # Cache for detected plates: car_id -> dict
        self.plate_cache = defaultdict(dict)

        # Async OCR worker
        self.ocr_queue = queue.Queue(maxsize=20)
        self.running = True
        self.ocr_thread = threading.Thread(target=self._ocr_worker, daemon=True)
        self.ocr_thread.start()

        # Active recording session state
        self.is_recording = False
        self.active_writer = None
        self.active_video_path = None
        self.active_target_plate = None
        self.active_target_car_id = None
        self.last_detection_timestamp = 0
        self.recorded_events = set()  # Set of (car_id, plate_text) to avoid duplicate file floods

    def _init_csv(self):
        """Ensure CSV exists with standard header."""
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            if os.stat(self.csv_file).st_size == 0 if os.path.exists(self.csv_file) else True:
                writer.writerow([
                    'timestamp',
                    'car_id',
                    'license_plate_number',
                    'confidence_score',
                    'snapshot_file',
                    'video_file',
                    'car_bbox',
                    'plate_bbox'
                ])

    def _log_detection_to_csv(self, car_id, plate_text, score, snapshot_file, video_file, car_bbox, plate_bbox):
        """Thread-safe CSV logging."""
        with self.csv_lock:
            with open(self.csv_file, 'a', newline='') as f:
                writer = csv.writer(f)
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                car_bbox_str = f"[{car_bbox[0]} {car_bbox[1]} {car_bbox[2]} {car_bbox[3]}]" if car_bbox else ""
                plate_bbox_str = f"[{plate_bbox[0]} {plate_bbox[1]} {plate_bbox[2]} {plate_bbox[3]}]" if plate_bbox else ""
                writer.writerow([
                    now_str,
                    car_id,
                    plate_text,
                    f"{score:.4f}",
                    snapshot_file,
                    video_file,
                    car_bbox_str,
                    plate_bbox_str
                ])

    def _ocr_worker(self):
        """Asynchronous OCR worker."""
        while self.running:
            try:
                task = self.ocr_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            car_id, plate_crop, full_frame, car_bbox, plate_bbox = task
            try:
                plate_gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
                _, plate_thresh = cv2.threshold(plate_gray, 64, 255, cv2.THRESH_BINARY_INV)

                text, score = read_license_plate(plate_thresh)
                if text is None:
                    text, score = read_license_plate(plate_gray)

                if text is not None and score >= self.min_ocr_score:
                    cached = self.plate_cache[car_id]
                    prev_score = cached.get('score', 0.0)

                    if score > prev_score or cached.get('text') is None:
                        # Resize crop for preview thumbnail
                        h, w = plate_crop.shape[:2]
                        thumb_w = max(1, int(w * 80 / max(h, 1)))
                        thumb = cv2.resize(plate_crop, (thumb_w, 80))

                        self.plate_cache[car_id] = {
                            'text': text,
                            'score': score,
                            'crop': thumb,
                            'plate_crop_full': plate_crop.copy(),
                            'full_frame': full_frame.copy(),
                            'car_bbox': car_bbox,
                            'plate_bbox': plate_bbox,
                            'last_seen': time.time(),
                            'logged': False
                        }
            except Exception as e:
                pass
            finally:
                self.ocr_queue.task_done()

    def _start_recording(self, car_id, plate_text, frame_shape, fps, pre_buffer):
        """Starts video recording with buffered lead-up frames."""
        now_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_plate = "".join(c for c in plate_text if c.isalnum()) or "UNKNOWN"
        video_filename = f"rec_car{car_id}_{safe_plate}_{now_tag}.mp4"
        self.active_video_path = os.path.join(self.videos_dir, video_filename)

        h, w = frame_shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.active_writer = cv2.VideoWriter(self.active_video_path, fourcc, max(10, int(fps)), (w, h))

        # Write buffered frames (pre-roll)
        for old_frame in pre_buffer:
            self.active_writer.write(old_frame)

        self.is_recording = True
        self.active_target_plate = plate_text
        self.active_target_car_id = car_id
        self.last_detection_timestamp = time.time()
        print(f"\n[🔴 REC STARTED] License Plate: {plate_text} (Car #{car_id}) -> {self.active_video_path}")

    def _stop_recording(self):
        """Closes video writer gracefully."""
        if self.active_writer is not None:
            self.active_writer.release()
            self.active_writer = None
            print(f"[⏹️ REC SAVED] Video saved to: {self.active_video_path}\n")
        self.is_recording = False
        self.active_video_path = None
        self.active_target_plate = None
        self.active_target_car_id = None

    def run(self):
        with mss.MSS() as sct:
            if self.monitor_index >= len(sct.monitors):
                print(f"[!] Error: Monitor index {self.monitor_index} not found. Available monitors: {len(sct.monitors)-1}")
                return

            monitor = sct.monitors[self.monitor_index]
            print(f"[*] Capturing screen region: {monitor['width']}x{monitor['height']} at ({monitor['left']},{monitor['top']})")

            window_name = "Screen ANPR - Auto Recording Monitor"
            if self.show_preview:
                cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
                cv2.resizeWindow(window_name, 1200, 700)

            # Circular pre-roll frame buffer (approx 2 seconds)
            pre_buffer_maxlen = int(self.pre_buffer_seconds * 20)
            pre_buffer = collections.deque(maxlen=pre_buffer_maxlen)

            fps_prev_time = time.time()
            fps = 20.0
            frame_nmr = 0

            print("[*] Screen capture active. Watching for number plates...")
            print("[*] Press 'q' or 'ESC' on the preview window to exit.\n")

            while self.running:
                loop_start = time.time()
                frame_nmr += 1

                # 1. Grab Screen Frame
                sct_img = sct.grab(monitor)
                frame = np.array(sct_img)
                # Convert BGRA to BGR
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                h, w, _ = frame.shape

                # Store raw frame in pre-roll buffer
                pre_buffer.append(frame.copy())

                # 2. Vehicle Detection
                coco_results = self.coco_model(frame, verbose=False, device=DEVICE)[0]
                detections = []
                for det in coco_results.boxes.data.tolist():
                    x1, y1, x2, y2, score, class_id = det
                    if int(class_id) in self.vehicles_classes and score > 0.35:
                        detections.append([x1, y1, x2, y2, score])

                # 3. Track Vehicles
                if len(detections) > 0:
                    track_ids = self.mot_tracker.update(np.asarray(detections))
                else:
                    track_ids = self.mot_tracker.update()

                # 4. Plate Detection
                plate_results = self.license_plate_detector(frame, verbose=False, device=DEVICE)[0]
                active_plates_in_frame = []

                for plate_det in plate_results.boxes.data.tolist():
                    x1, y1, x2, y2, plate_score, class_id = plate_det
                    if plate_score < 0.3:
                        continue

                    # Associate plate to vehicle
                    xcar1, ycar1, xcar2, ycar2, car_id = get_car(plate_det, track_ids)
                    if car_id != -1:
                        car_id = int(car_id)
                        crop = frame[max(0, int(y1)):min(h, int(y2)), max(0, int(x1)):min(w, int(x2))]
                        if crop.size > 0 and not self.ocr_queue.full():
                            car_bbox = [int(xcar1), int(ycar1), int(xcar2), int(ycar2)]
                            plate_bbox = [int(x1), int(y1), int(x2), int(y2)]
                            try:
                                self.ocr_queue.put_nowait((car_id, crop.copy(), frame.copy(), car_bbox, plate_bbox))
                            except queue.Full:
                                pass

                        # Check if plate has recognized text
                        plate_info = self.plate_cache.get(car_id)
                        if plate_info and plate_info.get('text'):
                            active_plates_in_frame.append((car_id, plate_info['text'], plate_info['score']))

                # 5. Check Recording Trigger & Snapshots
                current_time = time.time()

                for car_id, plate_text, plate_score in active_plates_in_frame:
                    self.last_detection_timestamp = current_time
                    event_key = (car_id, plate_text)

                    # Save snapshot and CSV entry on first confident identification
                    plate_info = self.plate_cache[car_id]
                    if not plate_info.get('logged'):
                        plate_info['logged'] = True
                        now_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_plate = "".join(c for c in plate_text if c.isalnum()) or "PLATE"
                        
                        snap_name = f"snap_car{car_id}_{safe_plate}_{now_tag}.jpg"
                        snap_path = os.path.join(self.snapshots_dir, snap_name)
                        
                        # Save full frame snapshot
                        if 'full_frame' in plate_info:
                            cv2.imwrite(snap_path, plate_info['full_frame'])

                        # Save cropped plate image
                        crop_name = f"crop_car{car_id}_{safe_plate}_{now_tag}.jpg"
                        crop_path = os.path.join(self.snapshots_dir, crop_name)
                        if 'plate_crop_full' in plate_info:
                            cv2.imwrite(crop_path, plate_info['plate_crop_full'])

                        vid_name = os.path.basename(self.active_video_path) if self.active_video_path else "pending"
                        self._log_detection_to_csv(
                            car_id=car_id,
                            plate_text=plate_text,
                            score=plate_score,
                            snapshot_file=snap_name,
                            video_file=vid_name,
                            car_bbox=plate_info.get('car_bbox'),
                            plate_bbox=plate_info.get('plate_bbox')
                        )
                        print(f"[📸 SNAPSHOT SAVED] Plate: {plate_text} (Score: {plate_score:.2f}) -> {snap_path}")

                    # Trigger Video Recording if not already recording
                    if not self.is_recording:
                        self._start_recording(car_id, plate_text, frame.shape, fps, pre_buffer)

                # Write frame to active recording video
                if self.is_recording and self.active_writer is not None:
                    self.active_writer.write(frame)

                    # Check cooldown
                    time_since_last_detect = current_time - self.last_detection_timestamp
                    if time_since_last_detect > self.post_record_seconds:
                        self._stop_recording()

                # 6. Build Display / HUD Preview
                if self.show_preview:
                    display_frame = frame.copy()

                    # Draw vehicle bounding boxes
                    for track in track_ids:
                        tx1, ty1, tx2, ty2, car_id = map(int, track[:5])
                        cv2.rectangle(display_frame, (tx1, ty1), (tx2, ty2), (0, 255, 0), 2)
                        
                        plate_info = self.plate_cache.get(car_id)
                        label = f"Vehicle #{car_id}"
                        if plate_info and plate_info.get('text'):
                            label += f" | Plate: {plate_info['text']} ({plate_info['score']:.2f})"

                        # Label badge
                        (lbl_w, lbl_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                        cv2.rectangle(display_frame, (tx1, max(0, ty1 - lbl_h - 10)),
                                      (tx1 + lbl_w + 10, ty1), (0, 180, 0), -1)
                        cv2.putText(display_frame, label, (tx1 + 5, ty1 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                    # Top Status Banner
                    banner_h = 55
                    cv2.rectangle(display_frame, (0, 0), (w, banner_h), (25, 25, 25), -1)

                    if self.is_recording:
                        # Flashing Red recording indicator
                        blink = int(current_time * 2) % 2 == 0
                        dot_color = (0, 0, 255) if blink else (50, 50, 200)
                        cv2.circle(display_frame, (30, 28), 10, dot_color, -1)
                        status_text = f"REC ACTIVE: Target {self.active_target_plate} (Car #{self.active_target_car_id})"
                        cv2.putText(display_frame, status_text, (50, 36),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 100, 255), 2)
                    else:
                        cv2.circle(display_frame, (30, 28), 10, (0, 220, 0), -1)
                        cv2.putText(display_frame, "SCREEN ANPR MONITORING (Waiting for number plates...)",
                                    (50, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)

                    # FPS & Device info
                    curr_time = time.time()
                    fps = 1.0 / (curr_time - fps_prev_time) if curr_time > fps_prev_time else fps
                    fps_prev_time = curr_time
                    info_text = f"FPS: {fps:.1f} | Device: {DEVICE}"
                    cv2.putText(display_frame, info_text, (w - 300, 36),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

                    cv2.imshow(window_name, display_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q') or key == 27:
                        break

            # Cleanup
            self.running = False
            if self.is_recording:
                self._stop_recording()
            if self.show_preview:
                cv2.destroyAllWindows()
            print("[*] Screen ANPR monitoring stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Continuous Screen Capture & Auto Number Plate Video Recorder")
    parser.add_argument("--monitor", type=int, default=1,
                        help="Monitor index to capture (default: 1 for primary monitor)")
    parser.add_argument("--output-dir", type=str, default="recordings",
                        help="Directory to save video clips, snapshots, and CSV (default: recordings)")
    parser.add_argument("--pre-buffer", type=float, default=2.0,
                        help="Pre-buffer duration in seconds before detection (default: 2.0)")
    parser.add_argument("--cooldown", type=float, default=4.0,
                        help="Seconds to keep recording after plate disappears (default: 4.0)")
    parser.add_argument("--min-score", type=float, default=0.25,
                        help="Minimum OCR confidence to trigger recording (default: 0.25)")
    parser.add_argument("--no-preview", action="store_true",
                        help="Run in headless background mode without preview GUI")
    parser.add_argument("--plate-model", type=str, default="./models/license_plate_detector.pt",
                        help="Path to YOLO license plate detector weights")
    parser.add_argument("--coco-model", type=str, default="yolov8n.pt",
                        help="Path to YOLO COCO weights")
    args = parser.parse_args()

    recorder = ScreenANPRRecorder(
        monitor_index=args.monitor,
        output_dir=args.output_dir,
        pre_buffer_seconds=args.pre_buffer,
        post_record_seconds=args.cooldown,
        min_ocr_score=args.min_score,
        show_preview=not args.no_preview,
        plate_model_path=args.plate_model,
        coco_model_path=args.coco_model
    )
    recorder.run()
