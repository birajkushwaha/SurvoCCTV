---
title: SurvoCCTV
emoji: 📹
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# SurvoCCTV - AI-Powered Store Intelligence System


SurvoCCTV is an end-to-end computer vision and analytics platform that translates raw CCTV video footage and POS transaction logs into actionable store intelligence. The system features a real-time tracking pipeline, a rule-based anomaly detector, and a modern, high-performance glassmorphic dark-themed dashboard.

---

## 🚀 Key Features

*   **Real-Time CCTV Multi-Stream Processing**: Concurrent decoding and object tracking across five logical camera zones (Entrance/Exit, Aisle 1, Aisle 2, Cashier Queue 1, Cashier Queue 2).
*   **Intelligent Spatial Analytics**: Multi-polygon zone classifier evaluating customer trajectory, dwell times, and aisle interaction rates.
*   **Operational Anomaly Alerts**: Real-time detectors flagging loitering (theft risk), cashier queue overflows, after-hours intrusion, and customer fall detection.
*   **POS Transaction Analytics**: Integration of point-of-sale data to calculate store conversion rates and identify revenue patterns.
*   **Glassmorphic Analytics Dashboard**: Interactive dark-themed web interface featuring live video streams, real-time alert toast notifications, historical analytics charts, and a canvas-rendered customer occupancy heatmap.
*   **Dockerized Deployment**: Fully containerized setup via Docker Compose for easy deployment.

---

## 🛠️ System Architecture & Design Choices

For details on the technical design and engineering trade-offs of the system:
*   📄 **[DESIGN.md](file:///c:/Users/biraj/Desktop/CCTV_Dection_Project/DESIGN.md)**: High-level architecture, module details, spatial coordinates, and database schema diagrams.
*   📄 **[CHOICES.md](file:///c:/Users/biraj/Desktop/CCTV_Dection_Project/CHOICES.md)**: Rationale behind choosing YOLOv8n, ByteTrack, SQLite, FastAPI, and vanilla frontend stack.

---

## 📦 Project Structure

```text
SurvoCCTV/
├── backend/
│   └── app/
│       ├── main.py            # FastAPI main entrypoint (REST & WebSockets)
│       ├── database.py        # SQLite connection, schemas, and POS CSV loader
│       ├── pipeline.py        # YOLOv8 + ByteTrack camera processor threads
│       ├── zones.py           # Polygonal zone definitions & overlays
│       ├── anomalies.py       # Heuristics for falls, loitering, and overflows
│       └── schemas.py         # Pydantic data schemas
├── frontend/
│   ├── index.html             # Glassmorphic Dark UI Layout
│   ├── style.css              # Styling, layouts, animations, and alert flashes
│   └── app.js                 # WebSocket telemetry and Chart.js UI handlers
├── scripts/
│   └── install_deps.py        # Pre-install script for virtual environments
├── data/                      # Data folder (Excluded from Git; populated locally)
│   ├── store_intelligence.db  # SQLite database file
│   ├── POS_Transactions.csv   # Imported transaction log
│   └── Store_Layout.xlsx      # Store layout blueprint
├── Dockerfile                 # Backend image build definition
├── docker-compose.yml         # Multi-container service config
├── DESIGN.md                  # System design document
├── CHOICES.md                 # Engineering decisions document
└── .gitignore                 # Exclusion rules (ignores videos, weights, and raw CSVs)
```

---

## ⚡ Quick Start

### Option 1: Docker Compose (Recommended)

To run the entire system inside Docker container services:

1.  Place the database resource files (`POS_Transactions.csv` and `Store_Layout.xlsx`) inside the `data/` directory.
2.  Place the raw video clips inside `data/CCTV Footage/` (named `cam_1.mp4` through `cam_5.mp4`).
3.  Build and run the containers:
    ```bash
    docker compose up --build
    ```
4.  Open your browser and navigate to **[http://localhost:8000](http://localhost:8000)**.

### Option 2: Running Locally

If running outside Docker:

1.  **Create a Virtual Environment & Activate it**:
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```
2.  **Install Dependencies**:
    ```bash
    python scripts/install_deps.py
    ```
3.  **Run the FastAPI App**:
    ```bash
    uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
    ```
4.  Navigate to **[http://localhost:8000](http://localhost:8000)**.

---

## 📊 API Reference

*   `GET /metrics` or `/api/metrics`: Exposes evaluation metrics, store occupancy, average dwell times, and conversion rates.
*   `GET /funnel` or `/api/funnel`: Generates stage conversion flow (`Entrance -> Browse -> Queue -> Purchase`).
*   `GET /api/pos-analytics`: Summarizes revenue performance by category and time of day.
*   `WS /api/ws`: Real-time WebSocket event broadcaster for live telemetry and security logs.
