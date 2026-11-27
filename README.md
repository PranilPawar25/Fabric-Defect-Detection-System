# AI-Based Fabric Defect Detection System

A full-stack, locally-runnable fabric quality inspection system for textile manufacturing. Automatically detects and classifies defects (holes, stains, knots, double knots, and broken threads) in fabric images and videos using unsupervised anomaly detection with a convolutional autoencoder.

## 🎯 Project Overview

This system is designed for college projects and real-world textile quality control. It works on standard consumer laptops (CPU-only) and requires **no labeled defect datasets** — it learns from clean fabric examples only.

### Key Features

- **Dual-Mode Detection**
  - **Autoencoder Mode**: Learned anomaly detection from clean fabric patterns
  - **Heuristic Fallback**: OpenCV-based detection (works before training)
  
- **Real-Time Analysis**
  - Single image upload and analysis
  - Video processing with progress tracking
  - Live camera stream support (IP Webcam)
  
- **Automatic Classification**
  - 5 defect types based on shape heuristics
  - Color-coded bounding boxes with confidence scores
  
- **Fabric Length Tracking**
  - Estimates defect position on fabric roll
  - Configurable feed speed (meters/minute)
  
- **Persistent Logging**
  - SQLite database for all detections
  - CSV export for quality reports
  - Statistics dashboard

### Technology Stack

- **Backend**: Python 3.10+, FastAPI, PyTorch (CPU), OpenCV
- **Frontend**: HTML/CSS/JavaScript (vanilla, no frameworks)
- **Database**: SQLite
- **ML**: Convolutional Autoencoder for unsupervised anomaly detection

---

## 📁 Project Structure

```
fabric-defect-system/
├── backend/
│   ├── main.py                      # FastAPI server entry point
│   ├── config.py                    # Configuration parameters
│   ├── models/
│   │   └── autoencoder.py           # PyTorch autoencoder model
│   ├── training/
│   │   ├── extract_patches.py       # Training data preparation
│   │   └── train_autoencoder.py     # Model training script
│   ├── inference/
│   │   ├── detector.py              # Core detection engine
│   │   ├── classifier.py            # Defect type classification
│   │   └── length_tracker.py        # Fabric position tracking
│   ├── api/
│   │   ├── routes_image.py          # Image analysis endpoints
│   │   ├── routes_video.py          # Video/stream endpoints
│   │   ├── routes_log.py            # Log retrieval/export
│   │   └── routes_config.py         # Configuration endpoints
│   └── db/
│       └── log_store.py             # SQLite database layer
├── frontend/
│   ├── index.html                   # Web UI
│   ├── style.css                    # Styling
│   └── app.js                       # Frontend logic
├── data/
│   ├── clean_fabric_videos/         # Place clean fabric videos here
│   ├── patches/                     # Auto-generated training patches
│   └── validation_patches/          # Auto-generated validation patches
├── trained_models/
│   ├── autoencoder.pt               # Saved model weights
│   └── threshold_stats.json         # Anomaly detection thresholds
├── requirements.txt
├── run.sh / run.bat                 # Launch scripts
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10 or later**
- **pip** (Python package manager)
- **(Optional) uv** for faster package installation

### Installation

#### 1. Clone or Download the Project

```bash
cd fabric-defect-system
```

#### 2. Run the Application

The system includes automatic setup scripts:

**Windows:**
```cmd
run.bat
```

**Linux/Mac:**
```bash
chmod +x run.sh
./run.sh
```

These scripts will:
- Create a virtual environment
- Install all dependencies from `requirements.txt`
- Start the FastAPI server

#### 3. Access the Web UI

Open your browser and navigate to:
```
http://localhost:8000
```

You should see the Fabric Defect Detection System interface.

---

## 📚 Usage Guide

### Phase 1: Using Heuristic Fallback Mode (No Training Required)

The system starts in **heuristic fallback mode** using OpenCV-based detection. This lets you demo the system immediately without training data.

1. **Upload a fabric image** via the "Image Analysis" tab
2. Click "Analyze Image"
3. View detected defects with bounding boxes and classifications
4. Check the defect log for detailed results

### Phase 2: Training the Autoencoder (For Better Accuracy)

To enable the more accurate **autoencoder mode**, you need to train the model on clean fabric footage.

#### Step 1: Collect Clean Fabric Videos

Record videos or take photos of **defect-free fabric only**. Requirements:
- Good lighting, consistent background
- Fabric fills most of the frame
- Multiple angles/positions (for variety)
- At least 30-60 seconds of video or 50+ images

Place your files in:
```
data/clean_fabric_videos/
```

#### Step 2: Extract Training Patches

```bash
cd backend
python training/extract_patches.py --input ../data/clean_fabric_videos/
```

**Options:**
```bash
# Custom patch size
python training/extract_patches.py --input video.mp4 --patch-size 64

# Custom frame interval (extract every 0.5 seconds)
python training/extract_patches.py --input video.mp4 --interval 0.5

# Clear existing patches before extraction
python training/extract_patches.py --input video.mp4 --clear
```

This will:
- Extract frames at regular intervals
- Split frames into 64×64 patches
- Save training patches to `data/patches/`
- Save validation patches to `data/validation_patches/`

#### Step 3: Train the Autoencoder

```bash
python training/train_autoencoder.py
```

**Training options:**
```bash
# Custom epochs and batch size
python training/train_autoencoder.py --epochs 100 --batch-size 64

# Custom learning rate
python training/train_autoencoder.py --lr 0.0001

# Resume with more epochs
python training/train_autoencoder.py --epochs 150
```

Training will:
- Train the autoencoder on clean patches
- Use early stopping (stops if no improvement)
- Save the best model to `trained_models/autoencoder.pt`
- Compute threshold statistics to `trained_models/threshold_stats.json`

**Expected Training Time:**
- CPU: 10-30 minutes for 50 epochs (depends on dataset size)
- GPU (if available): 2-5 minutes

#### Step 4: Restart the Server

After training completes, restart the server:
```bash
# Press Ctrl+C to stop the server, then run again:
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The system will now use **autoencoder mode** automatically.

---

## 🎮 Using the Web Interface

### Image Analysis Tab

1. Click "Choose Image" and select a fabric image
2. Click "Analyze Image"
3. View results:
   - Bounding boxes drawn on the image
   - Defect type and confidence for each detection
   - Updated statistics and log

### Video Analysis Tab

1. Click "Choose Video" and select a fabric video
2. Click "Analyze Video"
3. Wait for processing (progress bar shows status)
4. View aggregate results for the entire video

### Live Stream Tab

For real-time detection using a smartphone camera:

#### Option 1: HTTPS Mode (Recommended - Real Phone Camera)

**Use this for actual live detection with your phone's camera.**

1. **Start the HTTPS server:**
   ```bash
   run_live.bat
   ```

2. **On your laptop**, open: `https://localhost:8443`

3. **In the Live Stream tab**, click "Start Live Stream"
   - A QR code and phone URL will appear
   - URL format: `https://192.168.x.x:8443/live/phone?token=...`
   - ⚠️ Uses your actual LAN IP, **not localhost**

4. **On your phone** (same Wi-Fi network):
   - Scan the QR code OR copy and paste the URL
   - You'll see a certificate warning — tap "Advanced" → "Proceed" (this is expected for self-signed certificates)
   - Allow camera access when prompted
   - Tap "Start Camera"
   - Point at fabric → defects detected in real-time!

5. **Back on the laptop**, watch the stats update and defects appear in the log

**Troubleshooting Live Stream:**

- **"Camera permission denied"**: On your phone, tap the lock icon in the browser address bar → Permissions → Camera → Allow, then reload
- **Phone can't reach laptop**: 
  1. Ensure both devices are on the **same Wi-Fi network**
  2. Run this command **once** in Administrator PowerShell to allow Windows Firewall:
     ```powershell
     netsh advfirewall firewall add rule name="FabricLive8443" dir=in action=allow protocol=TCP localport=8443 profile=private
     ```
  3. Ensure Windows network is set to "Private" (not Public)
  4. If on college/public Wi-Fi with device isolation, use your phone's hotspot and connect the laptop to it

- **"Invalid link"**: The session expired. Start a new session on the laptop.

- **No LAN IP detected**: Connect the laptop to Wi-Fi or set `LIVE_HOST_IP` environment variable, then restart `run_live.bat`

**Why HTTPS is required**: Mobile browsers only allow camera access (`getUserMedia`) on secure connections (HTTPS or localhost). The system auto-generates a self-signed certificate for this.

#### Option 2: IP Webcam Mode (Legacy)

For using IP webcam apps instead of native camera:

1. **Install IP Webcam app** on your phone:
   - Android: [IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam)
   - iOS: Similar apps available

2. **Start the video stream** in the app
   - Note the URL shown (e.g., `http://192.168.1.100:8080/video`)

3. **Enter the URL** in the Live Stream tab
4. Set duration (how long to capture)
5. Click "Start Analysis"

### Detection Settings

Adjust parameters in the "Detection Settings" section:

- **Sensitivity (k_sigma)**: 
  - Higher = fewer false positives, may miss small defects
  - Lower = more detections, may include false positives
  - Range: 0.5 to 5.0 (default: 2.5)

- **Feed Speed**: 
  - Fabric speed in meters per minute
  - Used to estimate defect position on roll
  - Default: 10.0 m/min

- **Min Confidence**:
  - Minimum confidence to report a defect (%)
  - Range: 0 to 100 (default: 30%)

Click "Apply Settings" to update, or "Reset to Default" to restore defaults.

### Defect Log

- **View**: Scrollable log of all detected defects
- **Export CSV**: Download all logs as a CSV file
- **Clear Log**: Delete all logs (requires confirmation)

---

## 🔧 Configuration

All parameters can be customized in `backend/config.py`:

### Detection Parameters

```python
PATCH_SIZE = 64                    # Size of training/inference patches
K_SIGMA = 2.5                      # Anomaly threshold multiplier
MIN_CONFIDENCE = 30.0              # Minimum confidence to report
```

### Classification Thresholds

```python
BROKEN_THREAD_ASPECT_RATIO_MIN = 2.4   # Very elongated shapes
BROKEN_THREAD_ASPECT_RATIO_MAX = 0.42
KNOT_CIRCULARITY_THRESHOLD = 0.6       # How round a knot should be
```

### Training Parameters

```python
LEARNING_RATE = 0.001
BATCH_SIZE = 32
NUM_EPOCHS = 50
EARLY_STOPPING_PATIENCE = 10
```

---

## 📊 API Documentation

The system provides a REST API and WebSocket endpoints.

### REST API Endpoints

**Health Check**
```
GET /health
```

**Analyze Image**
```
POST /analyze/image
Body: multipart/form-data with 'file' field
Returns: JSON with detections
```

**Analyze Video**
```
POST /analyze/video
Body: multipart/form-data with 'file' field
Returns: JSON with all detections
```

**Analyze Live Stream**
```
POST /analyze/live
Body: {"stream_url": "http://...", "duration_seconds": 60}
Returns: JSON with detections
```

**Get Log**
```
GET /log/?limit=50
GET /log/?session_id=abc123
GET /log/?defect_type=hole
```

**Export Log**
```
GET /log/export
Returns: CSV file download
```

**Get/Update Configuration**
```
GET /config/
POST /config/
Body: {"k_sigma": 2.5, "feed_speed": 10.0, "min_confidence": 30.0}
```

### WebSocket Endpoint

**Real-Time Video Streaming**
```
WebSocket: /analyze/video/stream
```

1. Connect to WebSocket
2. Send config JSON: `{"feed_speed": 10.0, "save_to_log": true}`
3. Send video as binary data
4. Receive frame-by-frame results with annotated previews

Interactive API documentation available at:
```
http://localhost:8000/docs
```

---

## 🧪 Testing the Model

### Test Autoencoder Architecture

```bash
cd backend/models
python autoencoder.py
```

### Test Detector

```bash
cd backend/inference
python detector.py
```

### Test Classifier

```bash
cd backend/inference
python classifier.py
```

### Test Length Tracker

```bash
cd backend/inference
python length_tracker.py
```

---

## 🐛 Troubleshooting

### "No module named 'torch'"

Install PyTorch:
```bash
pip install torch torchvision
```

### "No patch files found"

Run the patch extraction script first:
```bash
python training/extract_patches.py --input data/clean_fabric_videos/
```

### "Could not open video file"

- Ensure video codec is supported (MP4 with H.264 is recommended)
- Try converting video: `ffmpeg -i input.avi -c:v libx264 output.mp4`

### Port 8000 Already in Use

Change the port in `backend/config.py`:
```python
API_PORT = 8001
```

Or specify when running:
```bash
python -m uvicorn main:app --port 8001
```

### Out of Memory During Training

Reduce batch size:
```bash
python training/train_autoencoder.py --batch-size 16
```

### System Running Slow

- The system is optimized for CPU-only operation
- For faster training, use a smaller `PATCH_SIZE` in config.py
- Process fewer frames: increase `VIDEO_PROCESSING_FPS` in config.py

---

## 📝 How It Works

### 1. Training Phase (Optional but Recommended)

- Extract patches from clean fabric videos
- Train a convolutional autoencoder to reconstruct clean patches
- Compute reconstruction error statistics (mean, std)
- Save model and threshold stats

### 2. Detection Phase

**Autoencoder Mode:**
- Split input image into patch grid
- Pass each patch through the trained autoencoder
- Compute reconstruction error for each patch
- Flag patches where error > mean + k×std as anomalous
- Merge adjacent anomalous patches into bounding boxes

**Heuristic Fallback Mode:**
- Compute brightness and edge density for each patch
- Calculate z-scores (deviation from mean)
- Flag patches with high z-scores as anomalous
- Merge into bounding boxes

### 3. Classification Phase

Use shape heuristics on each bounding box:
- **Aspect ratio** > 2.4 or < 0.42 → Broken Thread
- **Small + Circular** (1-2 patches) → Knot
- **Medium + Circular** (3-5 patches) → Double Knot
- **Large** (>5 patches) → Stain
- **Default** → Hole

### 4. Length Tracking

- Given video timestamp and feed speed
- Calculate: `length (m) = (feed_speed / 60) × elapsed_seconds`
- Attach fabric position to each logged defect

---

## ⚠️ Fabric Length Measurement: Limitations and Accuracy

### Important: This is an Estimate, Not an Exact Measurement

The system reports fabric length as an **estimate** based on a mathematical calculation, not a physical measurement. This is clearly labeled in the UI as "Est. @ X.XXm" to avoid false precision.

### How Length is Calculated

```
Estimated Length (meters) = (Feed Speed m/min ÷ 60) × Elapsed Time (seconds)
```

**Example:**
- Feed speed: 10 m/min
- Elapsed time: 12 seconds
- Estimated length: (10 / 60) × 12 = 2.0 meters

### Critical Assumption: Constant Feed Speed

**The system assumes the fabric moves at a CONSTANT speed throughout the entire video.**

This is a **software limitation** that cannot be fixed without additional hardware:
- ✅ **Works well when**: Fabric moves continuously at steady speed
- ❌ **Inaccurate when**: Fabric starts, stops, accelerates, or decelerates
- ❌ **Cannot detect**: Speed variations (no encoder/sensor to measure actual speed)

### Known Error Sources

1. **Variable Feed Speed** (not detectable by software alone)
   - Machine starts/stops during recording
   - Operator adjusts speed mid-run
   - Mechanical speed variations

2. **Video Timestamp Precision**
   - Depends on video codec and container format
   - Some formats may have less precise timestamps

3. **Manual Measurement Error**
   - When creating test footage for calibration
   - Ruler/tape measurement of real fabric length

4. **Frame Sampling**
   - System processes frames at intervals (not every frame)
   - Now uses actual video timestamps (fixed in latest version)
   - Previous versions incorrectly used frame-count assumptions

### Verification Tool

To measure accuracy for your specific setup, use the included calibration script:

```bash
cd backend
python training/verify_length_accuracy.py test_video.mp4 --real-length 2.0 --feed-speed 10.0
```

**How to create test footage:**
1. Physically measure a known length of fabric (e.g., 2.0 meters)
2. Mark start and end points
3. Set your feed speed (e.g., 10 m/min)
4. Record video of the fabric passing through
5. Stop when both marks have passed
6. Run the verification script

**Output example:**
```
ACCURACY VERIFICATION
======================================================================
Feed speed used: 10.00 m/min
Real measured length: 2.000 m

Using Current System Method (timestamp-based):
  Estimated length: 2.012 m
  Absolute error: +0.012 m
  Percentage error: +0.60%
  Assessment: ✅ EXCELLENT (< 1% error)
```

### Accuracy You Can Expect

Under **ideal conditions** (constant speed, good video codec):
- **Excellent**: < 1% error (system timestamp-based calculation is correct)
- **Good**: < 3% error
- **Acceptable**: < 5% error

Under **real-world conditions** (with speed variations):
- Accuracy depends entirely on how constant your feed speed actually is
- Software cannot compensate for physical speed changes
- Consider this when reporting results in your project

### Recommended: Document This Honestly

For college projects or industrial evaluation, **be transparent about this limitation**:

✅ **Good explanation:**
> "The system estimates fabric position based on elapsed time and user-provided feed speed. Under constant-speed conditions, this achieves <1% accuracy as verified by our test footage. However, the system cannot detect speed variations without additional hardware (encoder/sensor). Real-world accuracy depends on feed speed stability."

❌ **Bad explanation:**
> "The system precisely measures fabric position." (This overstates capability)

### Future Improvements (Requires Hardware)

To achieve true measurement accuracy:
- **Add a rotary encoder** on the feed roller
- **Add a proximity sensor** to count fabric length markings
- **Add a vision-based tracker** to measure fabric movement directly from video
- Any of these would eliminate the constant-speed assumption

---

## 🎓 For College Projects

### Presentation Tips

1. **Demo the heuristic fallback first** to show immediate functionality
2. **Explain the training process** with your clean fabric footage
3. **Show the improvement** from heuristic to autoencoder mode
4. **Demonstrate real-time detection** with live camera stream
5. **Export CSV** to show industrial applicability

### Key Points to Explain

- **Unsupervised Learning**: No labeled defects needed, learns from clean fabric only
- **Anomaly Detection**: Reconstruction error indicates abnormal patterns
- **Shape-Based Classification**: Geometric features distinguish defect types
- **Industrial Design**: Dark UI mimics real inspection systems
- **Scalability**: Local, CPU-only, no cloud dependency

### Suggested Improvements (for grading)

- Add more defect types with fine-tuned heuristics
- Implement SSIM loss for better reconstruction
- Add data augmentation during training
- Implement sliding window with overlap for better edge detection
- Add heat map visualization of anomaly scores

---

## 📄 License

This project is created for educational purposes. Feel free to modify and extend for your needs.

---

## 🙏 Acknowledgments

Built as a college project for textile quality inspection using AI and computer vision.

---

## 📧 Support

For issues or questions, please refer to the troubleshooting section or review the inline code comments — every major function is documented with purpose and usage.

---

**Project Status**: ✅ Complete and ready to run locally

**Last Updated**: 2026-09-04
