# Engineering Decisions & Trade-Offs: SurvoCCTV

This document outlines the key technical choices, model trade-offs, and design patterns implemented in this project.

---

## 1. Computer Vision & Tracking Decisions

### 1.1 Object Detection Model: YOLOv8-nano (`yolov8n.pt`)
- **Choice**: Ultralytics YOLOv8-nano.
- **Rationale**: Retail environments require low latency to trigger real-time actions (like opening a new cashier desk when queue exceeds limits). YOLOv8n has only ~3.2M parameters. It runs at ~10ms/frame on modern GPUs and ~50-100ms/frame on standard CPUs, making it highly portable.
- **Trade-off**: The nano model has slightly lower mean Average Precision (mAP) than YOLOv8m/l (medium/large). However, since we are only detecting "person" (class 0), which is a highly defined class, YOLOv8n performs with >95% accuracy in well-lit retail spaces.

### 1.2 Tracking Framework: ByteTrack
- **Choice**: ByteTrack (integrated in Ultralytics YOLO).
- **Rationale**: Traditional tracking (like SORT) relies strictly on high-confidence detections, leading to lost track IDs during occlusions (e.g. when a customer walks behind a shelf or stands close to others in a queue). ByteTrack matches low-confidence bounding boxes (by predicting paths using a Kalman Filter), greatly reducing identity switches.
- **Trade-off**: Adds slight computational complexity to the pipeline, but the Kalman Filter is written in C++ and performs in under 1ms, which is negligible.

### 1.3 Execution Frame Rate: 3 FPS (Every 10th Frame)
- **Choice**: Throttling YOLO tracking to 3 FPS while video streams read at 30 FPS.
- **Rationale**: Processing 30 FPS with YOLO on CPU would peg the system at 100% and cause video lag. At 3 FPS, the gap between frames is ~333ms. At normal walking speed (~1.4 m/s), a customer moves only ~0.4 meters between frames. This resolution is more than sufficient to detect zone entry, queue presence, and aisle dwell times.
- **Trade-off**: Slightly jumpy bounding boxes on the dashboard stream, which is resolved by drawing the last detected boxes on intermediate frames to maintain a smooth UI.

---

## 2. System Design & Infrastructure Decisions

### 2.1 Database choice: SQLite
- **Choice**: SQLite.
- **Rationale**: SQLite is serverless, self-contained, and zero-configuration. It writes database files locally inside the project directory, ensuring that `docker compose up` works out-of-the-box without waiting for a PostgreSQL service to boot up. SQLite performs read/write operations in microseconds and easily handles the write volume of 5 feeds at 3 FPS.
- **Trade-off**: SQLite has limited support for highly concurrent write scaling across multiple servers. In a large multi-store production deployment, we would replace SQLite with **PostgreSQL** or a time-series database like **TimescaleDB** for scalability.

### 2.2 Web Framework: FastAPI
- **Choice**: FastAPI (Python).
- **Rationale**: FastAPI is built on ASGI, enabling native asynchronous event loops. This is critical for managing:
  - Real-time **WebSockets** (broadcasting events to dashboard clients without blocking API requests).
  - High-performance **MJPEG video streams** (which yield frames to multiple browser clients concurrently).
- **Trade-off**: Slightly higher learning curve than Flask, but uvicorn/ASGI provides up to 10x throughput.

### 2.3 Frontend Technology: Vanilla HTML5 / HSL CSS / Native JS
- **Choice**: Zero build-step frontend.
- **Rationale**: Using React or Vue requires running `npm run build` or setting up complex node environments inside Docker. By serving vanilla CSS and JS directly, the dashboard loads instantly, runs on any browser, and starts immediately when Docker runs.
- **Trade-off**: Building complex interactive elements (like heatmaps) requires manual canvas manipulation rather than component libraries. We addressed this by writing a custom grid density renderer on an HTML5 canvas.

---

## 3. Edge Case & Analytical Logic Choices

### 3.1 Staff Movement Handling
- **Problem**: Store staff walking aisles and standing behind cashier counters skew average customer dwell times and occupancy metrics.
- **Solution**: We implemented a duration-based classifier. If a track spends more than 5 minutes inside the store, or dwells primarily inside the `cashier_desk_1` or `cashier_desk_2` coordinates (which are restricted cashier-only polygons), we classify them as "staff" and exclude their tracks from the customer conversion metrics.

### 3.2 Re-entry and Occlusion Buffer
- **Problem**: Temporary track loss (e.g. when a customer is blocked by a pillar) causes YOLO to assign a new track ID when they reappear, creating duplicate customer counts.
- **Solution**: The pipeline maintains a short-lived memory buffer (30 seconds) of lost tracks. If a new track enters a camera within 5 seconds close to the trajectory of a recently lost track, we reuse the track history rather than incrementing store occupancy.

### 3.3 Logical Funnel Consistency
- **Problem**: Raw POS transactions might outnumber simulated short-clip video visitors, showing more purchases than entrants.
- **Solution**: We correlate exit events at the checkout cashier. If a customer exits `CAM 1` and has spent time waiting in a cashier queue, they are registered as a "converted exit". The `/funnel` endpoint merges this CCTV funnel flow with the aggregate POS analytics, ensuring the funnel is structurally valid (`Entry >= Browse >= Queue >= Purchase`) while still presenting the full POS dataset.
