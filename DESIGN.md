# System Architecture Design: SurvoCCTV

This document outlines the architecture, data flow, and components of the AI-Powered SurvoCCTV System.

---

## 1. High-Level Architecture

The system follows a modular event-driven architecture, moving from raw video streams to live web dashboard telemetry:

```
[ CCTV Video Feeds (5 Cameras) ]
              │
              ▼  (Throttled at ~30 FPS, YOLOv8n Tracking at ~3 FPS)
[ Computer Vision Pipeline ] ──► (YOLOv8 BBoxes & ByteTrack Track IDs)
              │
              ▼
[ Spatial Zone Engine ] ──► (Point-in-Polygon checks: Entrance, Aisles, Queues)
              │
              ▼
[ Core Event Router ] ──► (Generates structured entry, exit, browse events)
       │              │
       ▼ (Async Save) ▼ (Real-time Broadcast)
[ SQLite Database ]   [ WebSocket Server ]
       │                      │
       ▼ (REST API Queries)   ▼ (WS Push Telemetry)
[      FastAPI REST & Streaming Web Services      ]
                      │
                      ▼
[ Modern Glassmorphism Dashboard UI (Frontend) ]
```

---

## 2. Core Components

### 2.1 Computer Vision & Spatial Engine (`backend/app/pipeline.py`, `backend/app/zones.py`)
- **Video Playback**: Spawns five background threads (one per camera) that read video frames and loop them to simulate continuous CCTV operation.
- **YOLOv8 Tracker**: Runs `yolov8n.pt` object tracking on every 10th frame (approx. 3 FPS) to keep CPU overhead low while maintaining track trajectories.
- **Zone Classifier**: Evaluates the center of each bounding box against polygon zones defined for each camera using OpenCV (`cv2.pointPolygonTest`). Classifies coordinates into `entrance`, `exit`, `aisle_1_shelves`, `aisle_2_shelves`, `cashier_queue_1`, or `cashier_queue_2`.

### 2.2 Business Logic & Anomaly Detector (`backend/app/anomalies.py`, `backend/app/database.py`)
- **Event Generator**: Detects zone transitions for track IDs (e.g. entering a cashier queue, visiting the cosmetics shelves, exiting the store). Emits structured events with payloads (like queue wait times and overall store dwell times).
- **Rule-Based Anomaly Engine**: Monitors real-time track telemetry:
  - **Queue Overflow**: Warns if the number of active tracks in a queue zone exceeds 4.
  - **Loitering / Theft Risk**: Triggers an alert if a customer dwells in a product shelf zone for more than 40 seconds.
  - **Fall Detection**: Flags a fall if a track's aspect ratio changes (height/width < 0.8) and they are near the ground.
  - **After-Hours Intrusion**: Triggers an alert if movement is detected when the store is closed.

### 2.3 Web Services & Streaming API (`backend/app/main.py`, `backend/app/schemas.py`)
- **FastAPI Core**: Serves the single-page dashboard at the root `/`.
- **REST Endpoints**:
  - `/metrics` & `/api/metrics`: Core KPI metrics.
  - `/funnel` & `/api/funnel`: Business funnel conversion stages.
  - `/api/events` & `/api/anomalies`: History databases.
  - `/api/pos-analytics`: POS revenue and category summaries.
- **WebSocket Gateway**: Maintains active connections and pushes real-time telemetry events.
- **MJPEG Streamer**: Streams frames containing YOLO bounding boxes and zone layouts to the dashboard via `/api/cameras/{camera_id}/stream`.

### 2.4 Live UI (`frontend/`)
- A premium, single-page dashboard designed using vanilla HTML5, modern HSL dark CSS variables, and native JavaScript.
- **Chart.js**: Visualizes live store occupancy trends and traffic distribution across product zones.
- **Heatmap Canvas**: Aggregates coordinate track histories from the database and draws a soft radial density cloud to show hotspots.
- **WebSockets**: Feeds the real-time event log and Toast notifier instantly.

---

## 3. Data Schemas

### 3.1 SQLite Schema

```sql
-- Structured store telemetry events
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE,
    timestamp TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    track_id INTEGER,
    event_type TEXT NOT NULL, -- entry, exit, queue_entry, queue_exit, shelf_interaction, anomaly
    zone TEXT,
    payload TEXT -- JSON string metadata
);

-- Store security and operational anomalies
CREATE TABLE anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_id TEXT UNIQUE,
    timestamp TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    track_id INTEGER,
    anomaly_type TEXT NOT NULL, -- loitering, queue_overflow, customer_fall, after_hours
    description TEXT,
    status TEXT DEFAULT 'active' -- active, resolved
);

-- Historical tracking coordinate buffer (for heatmaps)
CREATE TABLE tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    track_id INTEGER NOT NULL,
    x_center REAL NOT NULL,
    y_center REAL NOT NULL,
    width REAL NOT NULL,
    height REAL NOT NULL,
    zone TEXT
);

-- POS transaction records (imported from CSV)
CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT,
    order_time TEXT,
    customer_name TEXT,
    customer_number TEXT,
    product_name TEXT,
    brand_name TEXT,
    dep_name TEXT,
    sub_category TEXT,
    qty INTEGER,
    GMV REAL,
    NMV REAL,
    total_amount REAL
);
```
