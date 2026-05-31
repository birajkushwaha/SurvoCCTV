import os
import time
import cv2
import asyncio
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app import database, pipeline, schemas, zones

app = FastAPI(
    title="SurvoCCTV API",
    description="Real-time CCTV analytics, tracking telemetry, and anomaly detection",
    version="1.0.0"
)

# CORS middleware for local testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(FRONTEND_DIR, exist_ok=True)

# Mount frontend static directory if there are files in it
# We will serve index.html directly from root '/'
# We mount the frontend directory under /static to serve style.css and app.js
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"New WebSocket client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"WebSocket client disconnected. Total clients: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Connection might be dead
                pass

manager = ConnectionManager()

# Background task to broadcast events from the pipeline queue to all WS clients
async def event_broadcaster():
    print("Starting WebSocket event broadcaster background loop...")
    while True:
        if pipeline.pipeline_running:
            # We fetch from the pipeline generator
            async for event in pipeline.get_websocket_event_generator():
                await manager.broadcast(event)
        await asyncio.sleep(0.1)

@app.on_event("startup")
async def startup_event():
    # Initialize DB tables
    database.init_db()
    # Start the video pipelines automatically on startup
    pipeline.start_pipeline()
    # Spawn background task to push events to WebSocket
    asyncio.create_task(event_broadcaster())

@app.on_event("shutdown")
def shutdown_event():
    pipeline.stop_pipeline()

# ----------------- HTML VIEWS -----------------

@app.get("/", response_class=HTMLResponse)
async def read_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return """
    <html>
        <head><title>Store Intelligence System</title></head>
        <body style="font-family: sans-serif; text-align: center; padding-top: 50px; background-color: #0b0c10; color: #fff;">
            <h1>Store Intelligence System</h1>
            <p>Dashboard files are being generated. Please refresh in a moment.</p>
        </body>
    </html>
    """

# ----------------- REST API ENDPOINTS -----------------

@app.get("/api/cameras", response_model=List[schemas.CameraInfo])
async def get_cameras():
    cameras = [
        {"camera_id": "CAM 1", "name": "Entrance & Exit", "status": "online" if pipeline.pipeline_running else "offline", "fps": 3.0, "resolution": "1920x1080", "current_occupancy": 0},
        {"camera_id": "CAM 2", "name": "Aisle 1 - Cosmetics", "status": "online" if pipeline.pipeline_running else "offline", "fps": 3.0, "resolution": "1920x1080", "current_occupancy": 0},
        {"camera_id": "CAM 3", "name": "Aisle 2 - Skincare", "status": "online" if pipeline.pipeline_running else "offline", "fps": 3.0, "resolution": "1920x1080", "current_occupancy": 0},
        {"camera_id": "CAM 4", "name": "Cashier Desk 1", "status": "online" if pipeline.pipeline_running else "offline", "fps": 3.0, "resolution": "1920x1080", "current_occupancy": pipeline.queue_lengths.get("CAM 4", 0)},
        {"camera_id": "CAM 5", "name": "Cashier Desk 2", "status": "online" if pipeline.pipeline_running else "offline", "fps": 3.0, "resolution": "1920x1080", "current_occupancy": pipeline.queue_lengths.get("CAM 5", 0)}
    ]
    return cameras

@app.get("/metrics")
@app.get("/api/metrics", response_model=schemas.StoreMetrics)
async def get_metrics():
    db_metrics = database.get_store_metrics()
    return {
        "total_customers": db_metrics["total_customers"],
        "avg_dwell_seconds": db_metrics["avg_dwell_seconds"],
        "active_anomalies": db_metrics["active_anomalies"],
        "current_occupancy": pipeline.store_occupancy,
        "queue_lengths": pipeline.queue_lengths
    }

@app.get("/funnel")
@app.get("/api/funnel")
async def get_funnel():
    return database.get_funnel_stats()

@app.get("/api/pos-analytics")
async def get_pos_analytics():
    return database.get_pos_analytics()

@app.get("/api/events")
async def get_events(
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = None,
    camera_id: Optional[str] = None
):
    events = database.get_events(limit=limit, event_type=event_type, camera_id=camera_id)
    return events

@app.get("/api/anomalies", response_model=List[schemas.StoreAnomaly])
async def get_anomalies(
    limit: int = Query(30, ge=1, le=100),
    active_only: bool = False
):
    anomalies_list = database.get_anomalies(limit=limit, active_only=active_only)
    return anomalies_list

@app.post("/api/anomalies/{anomaly_id}/resolve")
async def resolve_anomaly(anomaly_id: str):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE anomalies SET status = 'resolved' WHERE anomaly_id = ?", (anomaly_id,))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    if rows_affected == 0:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    
    # Broadcast status change to websocket clients
    await manager.broadcast({
        "event_type": "anomaly_resolved",
        "timestamp": datetime.now().isoformat(),
        "data": {"anomaly_id": anomaly_id}
    })
    return {"status": "success", "message": "Anomaly marked as resolved"}

@app.get("/api/heatmap/{camera_id}")
async def get_heatmap(camera_id: str):
    if camera_id not in ["CAM 1", "CAM 2", "CAM 3", "CAM 4", "CAM 5"]:
        raise HTTPException(status_code=404, detail="Camera not found")
    points = database.get_heatmap_points(camera_id)
    return {"camera_id": camera_id, "points": points}

@app.post("/api/pipeline/start")
async def start_pipeline():
    if pipeline.pipeline_running:
        return {"status": "error", "message": "Pipeline is already running"}
    pipeline.start_pipeline()
    await manager.broadcast({
        "event_type": "pipeline_status",
        "timestamp": datetime.now().isoformat(),
        "data": {"status": "started"}
    })
    return {"status": "success", "message": "Pipeline started"}

@app.post("/api/pipeline/stop")
async def stop_pipeline_endpoint():
    if not pipeline.pipeline_running:
        return {"status": "error", "message": "Pipeline is not running"}
    pipeline.stop_pipeline()
    await manager.broadcast({
        "event_type": "pipeline_status",
        "timestamp": datetime.now().isoformat(),
        "data": {"status": "stopped"}
    })
    return {"status": "success", "message": "Pipeline stopped"}

# ----------------- MJPEG LIVE STREAMS -----------------

def generate_mjpeg_stream(camera_id: str):
    """Generator function that yields JPEG frames for MJPEG streaming."""
    print(f"Starting MJPEG stream for {camera_id}...")
    while True:
        # Check if pipeline is running
        if not pipeline.pipeline_running:
            # Yield offline screen or sleep
            time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            offline_img = zones.np.zeros((1080, 1920, 3), dtype=zones.np.uint8)
            cv2.putText(offline_img, f"CAMERA OFFLINE", (650, 500), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 4, cv2.LINE_AA)
            cv2.putText(offline_img, f"Start pipeline to activate stream. Time: {time_now}", (500, 600), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2, cv2.LINE_AA)
            ret, jpeg_bytes = cv2.imencode(".jpg", offline_img)
            if ret:
                frame_data = jpeg_bytes.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            time.sleep(1.0)
            continue

        # Get latest frame
        frame_data = pipeline.get_latest_frame(camera_id)
        if frame_data is None:
            time.sleep(0.1)
            continue
            
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
        # Throttling the stream to match YOLO output rate (approx. 10 FPS)
        time.sleep(0.05)

@app.get("/api/cameras/{camera_id}/stream")
async def stream_camera(camera_id: str):
    if camera_id not in ["CAM 1", "CAM 2", "CAM 3", "CAM 4", "CAM 5"]:
        raise HTTPException(status_code=404, detail="Camera not found")
        
    return StreamingResponse(
        generate_mjpeg_stream(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

# ----------------- WEBSOCKET ENDPOINT -----------------

@app.websocket("/api/ws/events")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Keep connection open. Read incoming client control messages if any.
        while True:
            data = await websocket.receive_text()
            # Handle client-to-server messages if needed
            print(f"Received WS message from client: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)
