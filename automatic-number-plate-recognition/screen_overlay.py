import argparse
import collections
import csv
import datetime
import os
import queue
import sys
import threading
import time
from collections import defaultdict

import cv2
import mss
import numpy as np
import torch
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPointF, QRectF
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QWidget
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


class OverlaySignal(QObject):
    update_data = pyqtSignal(list, list, dict, bool, str, float, int)


class ANPRScreenWorker(threading.Thread):
    def __init__(self, signal_emitter, monitor_index=1, output_dir="recordings",
                 continuous_record=True,
                 pre_buffer_seconds=2.0, post_record_seconds=4.0,
                 min_ocr_score=0.25,
                 plate_model_path='./models/license_plate_detector.pt',
                 coco_model_path='yolov8n.pt'):
        super().__init__(daemon=True)
        self.signal_emitter = signal_emitter
        self.monitor_index = monitor_index
        self.output_dir = output_dir
        self.snapshots_dir = os.path.join(output_dir, "snapshots")
        self.videos_dir = os.path.join(output_dir, "videos")
        os.makedirs(self.snapshots_dir, exist_ok=True)
        os.makedirs(self.videos_dir, exist_ok=True)

        self.continuous_record = continuous_record
        self.pre_buffer_seconds = pre_buffer_seconds
        self.post_record_seconds = post_record_seconds
        self.min_ocr_score = min_ocr_score

        self.csv_file = os.path.join(output_dir, "screen_detections.csv")
        self.csv_lock = threading.Lock()
        self._init_csv()

        print(f"[*] Initializing Screen Overlay ANPR on device: {DEVICE}")
        print(f"[*] Continuous Video Recording: {'ENABLED (Non-stop Full Session)' if self.continuous_record else 'EVENT TRIGGERED'}")
        
        self.coco_model = YOLO(coco_model_path)
        self.license_plate_detector = YOLO(plate_model_path)
        self.coco_model.to(DEVICE)
        self.license_plate_detector.to(DEVICE)

        self.mot_tracker = Sort(max_age=25, min_hits=2, iou_threshold=0.3)
        self.vehicles_classes = [2, 3, 5, 7]  # car, motorcycle, bus, truck

        self.plate_cache = defaultdict(dict)
        self.ocr_queue = queue.Queue(maxsize=20)
        self.running = True
        self.total_plates_detected = 0

        # OCR Thread
        self.ocr_thread = threading.Thread(target=self._ocr_worker, daemon=True)
        self.ocr_thread.start()

        # Video recording state
        self.is_recording = False
        self.active_writer = None
        self.active_video_path = None
        self.active_target_plate = ""
        self.active_target_car_id = None
        self.last_detection_timestamp = 0

    def _init_csv(self):
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            if not os.path.exists(self.csv_file) or os.stat(self.csv_file).st_size == 0:
                writer.writerow([
                    'timestamp',
                    'frame_nmr',
                    'car_id',
                    'license_plate_number',
                    'confidence_score',
                    'snapshot_file',
                    'video_file',
                    'car_bbox',
                    'plate_bbox'
                ])

    def _log_detection_to_csv(self, frame_nmr, car_id, plate_text, score, snapshot_file, video_file, car_bbox, plate_bbox):
        with self.csv_lock:
            with open(self.csv_file, 'a', newline='') as f:
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
                    snapshot_file,
                    video_file,
                    car_bbox_str,
                    plate_bbox_str
                ])

    def _ocr_worker(self):
        while self.running:
            try:
                task = self.ocr_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            car_id, plate_crop, full_frame, car_bbox, plate_bbox, frame_nmr = task
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
                        self.plate_cache[car_id] = {
                            'text': text,
                            'score': score,
                            'plate_crop_full': plate_crop.copy(),
                            'full_frame': full_frame.copy(),
                            'car_bbox': car_bbox,
                            'plate_bbox': plate_bbox,
                            'frame_nmr': frame_nmr,
                            'last_seen': time.time(),
                            'logged': False
                        }
            except Exception:
                pass
            finally:
                self.ocr_queue.task_done()

    def _init_continuous_writer(self, frame_shape, fps=20.0):
        now_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        video_filename = f"continuous_session_{now_tag}.mp4"
        self.active_video_path = os.path.join(self.videos_dir, video_filename)

        h, w = frame_shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.active_writer = cv2.VideoWriter(self.active_video_path, fourcc, max(10, int(fps)), (w, h))
        self.is_recording = True
        print(f"\n[🔴 CONTINUOUS RECORDING STARTED] Saving screen non-stop to: {self.active_video_path}")

    def _start_event_recording(self, car_id, plate_text, frame_shape, fps, pre_buffer):
        now_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_plate = "".join(c for c in plate_text if c.isalnum()) or "UNKNOWN"
        video_filename = f"rec_car{car_id}_{safe_plate}_{now_tag}.mp4"
        self.active_video_path = os.path.join(self.videos_dir, video_filename)

        h, w = frame_shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.active_writer = cv2.VideoWriter(self.active_video_path, fourcc, max(10, int(fps)), (w, h))

        for old_frame in pre_buffer:
            self.active_writer.write(old_frame)

        self.is_recording = True
        self.active_target_plate = plate_text
        self.active_target_car_id = car_id
        self.last_detection_timestamp = time.time()
        print(f"\n[🔴 EVENT REC STARTED] License Plate: {plate_text} (Car #{car_id}) -> {self.active_video_path}")

    def _stop_recording(self):
        if self.active_writer is not None:
            self.active_writer.release()
            self.active_writer = None
            print(f"[⏹️ REC SAVED] Video saved to: {self.active_video_path}\n")
        self.is_recording = False
        self.active_video_path = None
        self.active_target_plate = ""
        self.active_target_car_id = None

    def run(self):
        with mss.MSS() as sct:
            if self.monitor_index >= len(sct.monitors):
                print(f"[!] Error: Monitor index {self.monitor_index} not found.")
                return

            monitor = sct.monitors[self.monitor_index]
            pre_buffer_maxlen = int(self.pre_buffer_seconds * 20)
            pre_buffer = collections.deque(maxlen=pre_buffer_maxlen)

            fps_prev_time = time.time()
            fps = 20.0
            frame_nmr = 0

            # If continuous record, initialize writer on first frame
            if self.continuous_record:
                first_img = sct.grab(monitor)
                frame_first = np.array(first_img)
                self._init_continuous_writer(frame_first.shape, fps)

            while self.running:
                frame_nmr += 1
                # 1. Grab screen
                sct_img = sct.grab(monitor)
                frame = np.array(sct_img)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                h, w, _ = frame.shape
                pre_buffer.append(frame.copy())

                # 2. Write to continuous video if active
                if self.continuous_record and self.active_writer is not None:
                    self.active_writer.write(frame)

                # 3. Vehicle Detection
                coco_results = self.coco_model(frame, verbose=False, device=DEVICE)[0]
                detections = []
                for det in coco_results.boxes.data.tolist():
                    x1, y1, x2, y2, score, class_id = det
                    if int(class_id) in self.vehicles_classes and score > 0.35:
                        detections.append([x1, y1, x2, y2, score])

                # 4. Track Vehicles
                if len(detections) > 0:
                    track_ids = self.mot_tracker.update(np.asarray(detections))
                else:
                    track_ids = self.mot_tracker.update()

                # 5. Plate Detection
                plate_results = self.license_plate_detector(frame, verbose=False, device=DEVICE)[0]
                plate_boxes_overlay = []
                active_plates = []

                for plate_det in plate_results.boxes.data.tolist():
                    x1, y1, x2, y2, plate_score, class_id = plate_det
                    if plate_score < 0.3:
                        continue

                    plate_boxes_overlay.append([int(x1), int(y1), int(x2), int(y2), float(plate_score)])
                    xcar1, ycar1, xcar2, ycar2, car_id = get_car(plate_det, track_ids)
                    if car_id != -1:
                        car_id = int(car_id)
                        crop = frame[max(0, int(y1)):min(h, int(y2)), max(0, int(x1)):min(w, int(x2))]
                        if crop.size > 0 and not self.ocr_queue.full():
                            car_bbox = [int(xcar1), int(ycar1), int(xcar2), int(ycar2)]
                            plate_bbox = [int(x1), int(y1), int(x2), int(y2)]
                            try:
                                self.ocr_queue.put_nowait((car_id, crop.copy(), frame.copy(), car_bbox, plate_bbox, frame_nmr))
                            except queue.Full:
                                pass

                        plate_info = self.plate_cache.get(car_id)
                        if plate_info and plate_info.get('text'):
                            active_plates.append((car_id, plate_info['text'], plate_info['score']))

                # 6. Check Detections & Save Snapshots
                current_time = time.time()
                for car_id, plate_text, plate_score in active_plates:
                    self.last_detection_timestamp = current_time
                    self.active_target_plate = plate_text
                    self.active_target_car_id = car_id

                    plate_info = self.plate_cache[car_id]
                    if not plate_info.get('logged'):
                        plate_info['logged'] = True
                        self.total_plates_detected += 1
                        now_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_plate = "".join(c for c in plate_text if c.isalnum()) or "PLATE"

                        snap_name = f"snap_car{car_id}_{safe_plate}_{now_tag}.jpg"
                        snap_path = os.path.join(self.snapshots_dir, snap_name)
                        if 'full_frame' in plate_info:
                            cv2.imwrite(snap_path, plate_info['full_frame'])

                        crop_name = f"crop_car{car_id}_{safe_plate}_{now_tag}.jpg"
                        crop_path = os.path.join(self.snapshots_dir, crop_name)
                        if 'plate_crop_full' in plate_info:
                            cv2.imwrite(crop_path, plate_info['plate_crop_full'])

                        vid_name = os.path.basename(self.active_video_path) if self.active_video_path else "continuous"
                        self._log_detection_to_csv(
                            frame_nmr=plate_info.get('frame_nmr', frame_nmr),
                            car_id=car_id,
                            plate_text=plate_text,
                            score=plate_score,
                            snapshot_file=snap_name,
                            video_file=vid_name,
                            car_bbox=plate_info.get('car_bbox'),
                            plate_bbox=plate_info.get('plate_bbox')
                        )
                        print(f"[📸 SNAPSHOT SAVED] Plate: {plate_text} (Score: {plate_score:.2f}) -> {snap_path}")

                    # Event-based recording trigger
                    if not self.continuous_record and not self.is_recording:
                        self._start_event_recording(car_id, plate_text, frame.shape, fps, pre_buffer)

                # Event-based recording writer and cooldown
                if not self.continuous_record and self.is_recording and self.active_writer is not None:
                    self.active_writer.write(frame)
                    if (current_time - self.last_detection_timestamp) > self.post_record_seconds:
                        self._stop_recording()

                # Compute FPS
                curr_time = time.time()
                fps = 1.0 / (curr_time - fps_prev_time) if curr_time > fps_prev_time else fps
                fps_prev_time = curr_time

                # Convert track_ids to serializable list for Qt
                tracks_list = [[int(t[0]), int(t[1]), int(t[2]), int(t[3]), int(t[4])] for t in track_ids]
                
                target_str = self.active_target_plate if self.active_target_plate else ""
                self.signal_emitter.update_data.emit(
                    tracks_list,
                    plate_boxes_overlay,
                    dict(self.plate_cache),
                    self.is_recording,
                    target_str,
                    fps,
                    self.total_plates_detected
                )

                time.sleep(0.01)

        if self.is_recording:
            self._stop_recording()


class TransparentOverlayWindow(QWidget):
    def __init__(self, monitor_geometry, grab_width, grab_height, continuous_record=True):
        super().__init__()
        self.monitor_geometry = monitor_geometry
        self.grab_width = grab_width
        self.grab_height = grab_height
        self.continuous_record = continuous_record

        self.scale_x = monitor_geometry.width() / max(1, grab_width)
        self.scale_y = monitor_geometry.height() / max(1, grab_height)

        # Configure transparent, frameless, topmost, click-through overlay window
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )

        self.setGeometry(monitor_geometry)

        # State data for rendering
        self.tracks = []
        self.plates = []
        self.plate_cache = {}
        self.is_recording = False
        self.rec_target = ""
        self.fps = 0.0
        self.total_plates = 0

        # Continuous repaint timer for smooth glowing effects and animations
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(40)  # 25 FPS UI refresh

    def update_overlay(self, tracks, plates, plate_cache, is_recording, rec_target, fps, total_plates):
        self.tracks = tracks
        self.plates = plates
        self.plate_cache = plate_cache
        self.is_recording = is_recording
        self.rec_target = rec_target
        self.fps = fps
        self.total_plates = total_plates

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        current_time = time.time()

        # =====================================================================
        # 1. FULL SCREEN NEON GREEN BORDER & CORNER ACCENTS
        # =====================================================================
        border_thickness = 4
        border_color = QColor(0, 255, 120, 220)

        pen_border = QPen(border_color, border_thickness)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(2, 2, w - 4, h - 4)

        # Corner target brackets
        corner_len = 50
        pen_corner = QPen(border_color, border_thickness + 2)
        painter.setPen(pen_corner)

        # Top-Left
        painter.drawLine(2, 2, 2 + corner_len, 2)
        painter.drawLine(2, 2, 2, 2 + corner_len)
        # Top-Right
        painter.drawLine(w - 2 - corner_len, 2, w - 2, 2)
        painter.drawLine(w - 2, 2, w - 2, 2 + corner_len)
        # Bottom-Left
        painter.drawLine(2, h - 2, 2 + corner_len, h - 2)
        painter.drawLine(2, h - 2 - corner_len, 2, h - 2)
        # Bottom-Right
        painter.drawLine(w - 2 - corner_len, h - 2, w - 2, h - 2)
        painter.drawLine(w - 2, h - 2 - corner_len, w - 2, h - 2)

        # =====================================================================
        # 2. VEHICLE BOUNDING BOXES & BADGES
        # =====================================================================
        for track in self.tracks:
            tx1, ty1, tx2, ty2, car_id = track
            sx1 = int(tx1 * self.scale_x)
            sy1 = int(ty1 * self.scale_y)
            sx2 = int(tx2 * self.scale_x)
            sy2 = int(ty2 * self.scale_y)
            bw = sx2 - sx1
            bh = sy2 - sy1

            # Vehicle box
            pen = QPen(QColor(0, 255, 128, 230), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(QColor(0, 255, 128, 25))
            painter.drawRoundedRect(QRectF(sx1, sy1, bw, bh), 4, 4)

            # Plate badge
            plate_info = self.plate_cache.get(car_id)
            if plate_info and plate_info.get('text'):
                badge_text = f"🚗 #{car_id} | 🏷️ {plate_info['text']} ({plate_info['score']:.2f})"
                bg_color = QColor(10, 180, 50, 235)
            else:
                badge_text = f"🚗 Vehicle #{car_id}"
                bg_color = QColor(20, 20, 20, 210)

            painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(badge_text) + 16
            th = 24
            badge_y = max(10, sy1 - th - 4)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(QRectF(sx1, badge_y, tw, th), 4, 4)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(int(sx1 + 8), int(badge_y + 17), badge_text)

        # =====================================================================
        # 3. LICENSE PLATE BOUNDING BOXES
        # =====================================================================
        for plate in self.plates:
            px1, py1, px2, py2, score = plate
            spx1 = int(px1 * self.scale_x)
            spy1 = int(py1 * self.scale_y)
            spx2 = int(px2 * self.scale_x)
            spy2 = int(py2 * self.scale_y)
            pbw = spx2 - spx1
            pbh = spy2 - spy1

            pen_plate = QPen(QColor(255, 50, 50, 240), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen_plate)
            painter.setBrush(QColor(255, 0, 0, 35))
            painter.drawRoundedRect(QRectF(spx1, spy1, pbw, pbh), 3, 3)

        # =====================================================================
        # 4. TOP FLOATING GLASSMORPHISM HUD BAR
        # =====================================================================
        hud_w = 560
        hud_h = 44
        hud_x = int((w - hud_w) / 2)
        hud_y = 15

        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.setBrush(QColor(15, 15, 20, 225))
        painter.drawRoundedRect(QRectF(hud_x, hud_y, hud_w, hud_h), 10, 10)

        # Pulsing Red Dot when recording
        blink = int(current_time * 2.5) % 2 == 0
        dot_color = QColor(255, 30, 30, 255) if blink else QColor(160, 20, 20, 200)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_color)
        painter.drawEllipse(QPointF(hud_x + 22, hud_y + 22), 7, 7)

        painter.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        painter.setPen(QColor(255, 255, 255))
        
        if self.rec_target:
            hud_msg = f"REC ACTIVE: 🏷️ {self.rec_target} | Total: {self.total_plates}"
        else:
            hud_msg = f"CONTINUOUS REC ON | Detected Plates: {self.total_plates}"
        
        painter.drawText(hud_x + 38, hud_y + 27, hud_msg)

        # FPS counter on the right of HUD
        painter.setFont(QFont("Arial", 10, QFont.Weight.Normal))
        painter.setPen(QColor(160, 160, 170))
        painter.drawText(hud_x + hud_w - 85, hud_y + 27, f"{self.fps:.1f} FPS")


def main():
    parser = argparse.ArgumentParser(description="Continuous Screen Recording & ANPR Transparent Desktop Overlay")
    parser.add_argument("--monitor", type=int, default=1,
                        help="Monitor index to capture and overlay (default: 1)")
    parser.add_argument("--output-dir", type=str, default="recordings",
                        help="Directory to save continuous video, snapshots, and CSV (default: recordings)")
    parser.add_argument("--event-only", action="store_true",
                        help="Record video clips only on detection events rather than continuous full session")
    parser.add_argument("--min-score", type=float, default=0.25,
                        help="Minimum OCR confidence to log plate and snapshot (default: 0.25)")
    args = parser.parse_args()

    app = QApplication(sys.argv)

    # Get monitor resolution from MSS
    with mss.MSS() as sct:
        if args.monitor >= len(sct.monitors):
            print(f"[!] Invalid monitor index {args.monitor}")
            sys.exit(1)
        mon = sct.monitors[args.monitor]
        grab_w = mon['width']
        grab_h = mon['height']

    # Get Qt screen geometry
    screens = app.screens()
    screen_idx = min(args.monitor - 1, len(screens) - 1)
    target_screen = screens[screen_idx]
    screen_geometry = target_screen.geometry()

    print(f"[*] Target Screen Geometry: {screen_geometry.width()}x{screen_geometry.height()}")
    print(f"[*] Native Grab Resolution: {grab_w}x{grab_h}")

    continuous_mode = not args.event_only

    # Create Transparent Click-Through Overlay
    overlay = TransparentOverlayWindow(screen_geometry, grab_w, grab_h, continuous_record=continuous_mode)
    overlay.show()
    overlay.raise_()

    signal_emitter = OverlaySignal()
    signal_emitter.update_data.connect(overlay.update_overlay)

    # Start Background ANPR Screen Worker
    worker = ANPRScreenWorker(
        signal_emitter=signal_emitter,
        monitor_index=args.monitor,
        output_dir=args.output_dir,
        continuous_record=continuous_mode,
        min_ocr_score=args.min_score
    )
    worker.start()

    print("\n" + "="*60)
    print("🚀 CONTINUOUS SCREEN ANPR OVERLAY IS RUNNING!")
    print("🟢 GREEN BORDER: Visible around your screen with live cyber corners.")
    print("🔴 CONTINUOUS RECORDING: Full video session is recording non-stop to recordings/videos/.")
    print("📸 AUTO SNAPSHOTS & CSV: Every detected plate is saved automatically.")
    print("👉 All mouse clicks pass directly through to your apps & desktop.")
    print("👉 Press Ctrl+C in this terminal to stop and save the video.")
    print("="*60 + "\n")

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        worker.running = False
        print("[*] Overlay closed.")


if __name__ == "__main__":
    main()
