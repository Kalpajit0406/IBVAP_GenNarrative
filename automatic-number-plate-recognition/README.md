# automatic-number-plate-recognition-python-yolov8

<p align="center">
<a href="https://www.youtube.com/watch?v=fyJB1t0o0ms">
    <img width="600" src="https://utils-computervisiondeveloper.s3.amazonaws.com/thumbnails/with_play_button/anpr_yolo2.jpg" alt="Watch the video">
    </br>Watch on YouTube: Automatic number plate recognition with Python, Yolov8 and EasyOCR !
</a>
</p>

## data

The video I used in this tutorial can be downloaded [here](https://www.pexels.com/video/traffic-flow-in-the-highway-2103099/).

## models

A Yolov8 pretrained model was used to detect vehicles.

A licensed plate detector was used to detect license plates. The model was trained with Yolov8 using [this dataset](https://universe.roboflow.com/roboflow-universe-projects/license-plate-recognition-rxg4e/dataset/4) and following this [step by step tutorial on how to train an object detector with Yolov8 on your custom data](https://github.com/computervisioneng/train-yolov8-custom-dataset-step-by-step-guide). 

The trained model is available in my [Patreon](https://www.patreon.com/ComputerVisionEngineer).

## dependencies

The sort module needs to be downloaded from [this repository](https://github.com/abewley/sort) as mentioned in the [video](https://youtu.be/fyJB1t0o0ms?t=1120).

## Usage Modes

### 1. Continuous Transparent Screen Overlay & Auto-Recorder (`screen_overlay.py`)
Applies a **transparent HUD layer directly on top of your desktop screen** with a glowing green border.
- **Continuous Non-Stop Video Recording**: Records your full screen session into `recordings/videos/continuous_session_<timestamp>.mp4`.
- **Live AR Bounding Boxes & Badges**: Draws detection boxes directly over vehicles on your screen without blocking mouse clicks.
- **Auto Snapshots & CSV**: Automatically logs detected plates and saves full/cropped snapshots to `recordings/snapshots/` and `recordings/screen_detections.csv`.

```bash
python screen_overlay.py
```

### 2. Continuous Screen Capture with Auto-Record (`screen_recorder.py`)
Continuously monitors your desktop screen and automatically starts recording video clips and saving snapshots whenever a license plate is detected:
```bash
python screen_recorder.py
```

### 3. Live Camera / Webcam ANPR (`realtime.py`)
Run real-time vehicle and plate recognition with live HUD overlay:
```bash
python realtime.py
# or specify camera index/video:
python realtime.py --source 0
```

