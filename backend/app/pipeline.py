import os
import time
import queue
import threading
import uuid
import asyncio
from datetime import datetime
import cv2
from ultralytics import YOLO
from backend.app import database, zones, anomalies

# Queue for real-time dashboard events
event_queue = queue.Queue()

# Dict to hold the latest frame per camera for streaming
# format: {camera_id: JPEG byte string}
latest_frames = {}
frame_locks = {}

# System control status
pipeline_running = False
camera_threads = []

# Keep track of active tracks across frames for event generation
# format: {camera_id: {track_id: {"zone": zone_name, "first_seen": timestamp, "last_seen": timestamp}}}
_active_camera_tracks = {}

# Current occupancy states for metrics
store_occupancy = 0
queue_lengths = {"CAM 4": 0, "CAM 5": 0}

def get_latest_frame(camera_id):
    """Returns the latest processed JPEG frame for the camera stream."""
    return latest_frames.get(camera_id, None)

def put_event(event):
    """Puts an event in the thread-safe queue for WebSocket broadcast."""
    event_queue.put(event)

class CameraPipeline:
    def __init__(self, camera_id, video_path):
        self.camera_id = camera_id
        self.video_path = video_path
        self.model = None
        self.running = False
        frame_locks[camera_id] = threading.Lock()
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, name=f"Pipeline-{self.camera_id}")
        self.thread.daemon = True
        self.thread.start()
        
    def stop(self):
        self.running = False
        
    def _run_loop(self):
        print(f"[{self.camera_id}] Starting pipeline thread...")
        # Load YOLO model inside the thread to avoid multi-threading conflicts
        try:
            self.model = YOLO("yolov8n.pt")
            print(f"[{self.camera_id}] Loaded YOLOv8n model.")
        except Exception as e:
            print(f"[{self.camera_id}] Error loading model: {e}")
            self.running = False
            return

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"[{self.camera_id}] Error opening video: {self.video_path}")
            self.running = False
            return
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_time = 1.0 / fps if fps > 0 else 0.033
        frame_count = 0
        
        # Track states local to this camera
        if self.camera_id not in _active_camera_tracks:
            _active_camera_tracks[self.camera_id] = {}
            
        active_tracks = _active_camera_tracks[self.camera_id]
        
        # Bounding boxes from the last YOLO processing frame
        # format: {track_id: (x1, y1, x2, y2, zone_name)}
        last_boxes = {}
        
        while self.running and pipeline_running:
            start_time = time.time()
            ret, frame = cap.read()
            
            # Loop the video if it ends
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
                
            frame_count += 1
            
            # Draw defined zones on the frame (Entrance, Aisle, Cashier, etc.)
            frame = zones.draw_zones_on_frame(self.camera_id, frame)
            
            # Process with YOLO on every 10th frame to maintain real-time performance on CPU
            run_yolo = (frame_count % 10 == 0)
            
            current_people_in_zones = {}
            
            if run_yolo:
                # Run YOLO tracking (person class only: cls=0)
                # persist=True enables ByteTrack multi-object tracking
                results = self.model.track(frame, persist=True, classes=[0], verbose=False)
                
                new_boxes = {}
                active_track_ids_in_frame = set()
                
                if results and len(results) > 0 and results[0].boxes is not None:
                    boxes = results[0].boxes
                    for box in boxes:
                        # Extract box coordinates, class, tracking ID
                        if box.id is not None:
                            track_id = int(box.id[0])
                            active_track_ids_in_frame.add(track_id)
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            
                            # Center point
                            cx = int((x1 + x2) / 2)
                            cy = int((y1 + y2) / 2)
                            
                            # Determine zone
                            zone_name = zones.get_zone_at_point(self.camera_id, cx, cy)
                            new_boxes[track_id] = (x1, y1, x2, y2, zone_name)
                            
                            # Increment counters for metrics
                            if zone_name != "general":
                                current_people_in_zones[zone_name] = current_people_in_zones.get(zone_name, 0) + 1
                                
                            # Check database track logging (every 10 frames to avoid DB bloating)
                            now_iso = datetime.now().isoformat()
                            database.save_track(now_iso, self.camera_id, track_id, float(cx)/1920, float(cy)/1080, float(x2-x1)/1920, float(y2-y1)/1080, zone_name)
                            
                            # Check for zone transitions and events
                            self._process_track_events(track_id, zone_name, now_iso, active_tracks)
                            
                            # Run anomaly checks (fall, loitering)
                            anomaly = anomalies.update_track_state_and_check(
                                self.camera_id, track_id, zone_name, (cx, cy, x2-x1, y2-y1)
                            )
                            if anomaly:
                                put_event({
                                    "event_type": "anomaly",
                                    "timestamp": now_iso,
                                    "data": anomaly
                                })
                
                # Check for tracks that disappeared (exited store or camera view)
                disappeared_ids = set(active_tracks.keys()) - active_track_ids_in_frame
                for track_id in disappeared_ids:
                    # Trigger exit transition if they were inside
                    now_iso = datetime.now().isoformat()
                    self._handle_track_exit(track_id, now_iso, active_tracks)
                
                # Check anomalies local to zones (e.g. queue overflow)
                self._check_zone_anomalies(current_people_in_zones)
                
                last_boxes = new_boxes
            
            # Draw tracking bounding boxes on frame
            for track_id, (x1, y1, x2, y2, zone_name) in last_boxes.items():
                # Color based on zone
                color = zones.ZONE_COLORS.get(zone_name, (255, 255, 255))
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                
                # Label text
                label = f"Cust #{track_id}"
                if zone_name != "general":
                    label += f" ({zone_name.split('_')[-1].upper()})"
                cv2.putText(
                    frame, 
                    label, 
                    (x1, y1 - 8), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.5, 
                    color, 
                    2, 
                    cv2.LINE_AA
                )
                
            # Render stats directly on camera video feed for a raw CCTV feel
            cv2.putText(
                frame, 
                f"{self.camera_id} - LIVE FEED", 
                (30, 40), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                0.8, 
                (255, 255, 255), 
                2, 
                cv2.LINE_AA
            )
            
            # Encode frame to JPEG
            ret_encode, jpeg_bytes = cv2.imencode(".jpg", frame)
            if ret_encode:
                with frame_locks[self.camera_id]:
                    latest_frames[self.camera_id] = jpeg_bytes.tobytes()
                    
            # Throttling to match actual frame rate
            elapsed = time.time() - start_time
            sleep_time = max(0.001, frame_time - elapsed)
            time.sleep(sleep_time)
            
        cap.release()
        print(f"[{self.camera_id}] Pipeline thread stopped.")

    def _process_track_events(self, track_id, current_zone, timestamp, active_tracks):
        """Processes event triggers based on tracking spatial movements."""
        if track_id not in active_tracks:
            # 1. NEW TRACK detected by this camera
            active_tracks[track_id] = {
                "zone": current_zone,
                "first_seen": timestamp,
                "last_seen": timestamp
            }
            
            # If camera 1 (Entrance) and in entrance zone, it's a customer entry
            if self.camera_id == "CAM 1" and current_zone == "entrance":
                event_id = str(uuid.uuid4())
                database.save_event(event_id, timestamp, self.camera_id, track_id, "entry", current_zone)
                
                global store_occupancy
                store_occupancy += 1
                
                put_event({
                    "event_type": "entry",
                    "timestamp": timestamp,
                    "data": {
                        "event_id": event_id,
                        "camera_id": self.camera_id,
                        "track_id": track_id,
                        "zone": current_zone,
                        "store_occupancy": store_occupancy
                    }
                })
        else:
            # 2. EXISTING TRACK
            state = active_tracks[track_id]
            previous_zone = state["zone"]
            state["last_seen"] = timestamp
            
            if previous_zone != current_zone:
                state["zone"] = current_zone
                
                # Emit zone transition event
                event_id = str(uuid.uuid4())
                event_type = "zone_transition"
                
                # Custom label for queue and shelf entry
                if "queue" in current_zone:
                    event_type = "queue_entry"
                elif "shelves" in current_zone:
                    event_type = "shelf_interaction"
                elif "queue" in previous_zone:
                    event_type = "queue_exit"
                    # Calculate wait time
                    first_seen_dt = datetime.fromisoformat(state["first_seen"])
                    now_dt = datetime.fromisoformat(timestamp)
                    wait_sec = (now_dt - first_seen_dt).total_seconds()
                    
                # Save event
                payload = {}
                if event_type == "queue_exit":
                    payload["wait_seconds"] = round(wait_sec, 1)
                    
                database.save_event(event_id, timestamp, self.camera_id, track_id, event_type, current_zone, payload)
                
                put_event({
                    "event_type": event_type,
                    "timestamp": timestamp,
                    "data": {
                        "event_id": event_id,
                        "camera_id": self.camera_id,
                        "track_id": track_id,
                        "from_zone": previous_zone,
                        "to_zone": current_zone,
                        "payload": payload
                    }
                })

    def _handle_track_exit(self, track_id, timestamp, active_tracks):
        """Processes events when a track is lost/exits the view."""
        if track_id in active_tracks:
            state = active_tracks[track_id]
            last_zone = state["zone"]
            
            # If camera 1 (Exit camera) and was near the exit gate, trigger customer exit
            if self.camera_id == "CAM 1" and last_zone == "exit":
                # Calculate total store dwell time
                first_seen_dt = datetime.fromisoformat(state["first_seen"])
                now_dt = datetime.fromisoformat(timestamp)
                dwell_sec = (now_dt - first_seen_dt).total_seconds()
                
                event_id = str(uuid.uuid4())
                payload = {"duration_seconds": round(dwell_sec, 1)}
                database.save_event(event_id, timestamp, self.camera_id, track_id, "exit", last_zone, payload)
                
                global store_occupancy
                store_occupancy = max(0, store_occupancy - 1)
                
                put_event({
                    "event_type": "exit",
                    "timestamp": timestamp,
                    "data": {
                        "event_id": event_id,
                        "camera_id": self.camera_id,
                        "track_id": track_id,
                        "zone": last_zone,
                        "duration_seconds": round(dwell_sec, 1),
                        "store_occupancy": store_occupancy
                    }
                })
                
            # Clean up active state
            del active_tracks[track_id]

    def _check_zone_anomalies(self, people_in_zones):
        """Applies spatial aggregation anomaly rules (e.g. queue overflow)."""
        # Queue check for CAM 4 and CAM 5
        if self.camera_id == "CAM 4":
            count = people_in_zones.get("cashier_queue_1", 0)
            queue_lengths["CAM 4"] = count
            anomaly = anomalies.check_queue_overflow(self.camera_id, "cashier_queue_1", count)
            if anomaly:
                put_event({
                    "event_type": "anomaly",
                    "timestamp": datetime.now().isoformat(),
                    "data": anomaly
                })
        elif self.camera_id == "CAM 5":
            count = people_in_zones.get("cashier_queue_2", 0)
            queue_lengths["CAM 5"] = count
            anomaly = anomalies.check_queue_overflow(self.camera_id, "cashier_queue_2", count)
            if anomaly:
                put_event({
                    "event_type": "anomaly",
                    "timestamp": datetime.now().isoformat(),
                    "data": anomaly
                })

def start_pipeline():
    """Starts the background tracking pipeline for all 5 CCTV feeds."""
    global pipeline_running, camera_threads
    if pipeline_running:
        return
        
    pipeline_running = True
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    video_dir = os.path.join(BASE_DIR, "data", "CCTV Footage")
    
    cameras = [
        ("CAM 1", "CAM 1.mp4"),
        ("CAM 2", "CAM 2.mp4"),
        ("CAM 3", "CAM 3.mp4"),
        ("CAM 4", "CAM 4.mp4"),
        ("CAM 5", "CAM 5.mp4")
    ]
    
    # Clean stale anomalies or states from previous run
    anomalies._last_triggered.clear()
    anomalies._track_states.clear()
    
    for cam_id, filename in cameras:
        video_path = os.path.join(video_dir, filename)
        pipeline = CameraPipeline(cam_id, video_path)
        pipeline.start()
        camera_threads.append(pipeline)
        
    # Start thread to clean up stale track states in anomalies engine
    def cleanup_loop():
        while pipeline_running:
            anomalies.clean_stale_tracks()
            time.sleep(10)
            
    cleanup_thread = threading.Thread(target=cleanup_loop, name="Track-Cleanup")
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    print("Store Intelligence pipeline started successfully!")

def stop_pipeline():
    """Stops all running video processing pipelines."""
    global pipeline_running, camera_threads
    pipeline_running = False
    for thread in camera_threads:
        thread.stop()
    camera_threads.clear()
    print("Store Intelligence pipeline stopped.")

async def get_websocket_event_generator():
    """
    Asynchronously yields events from the pipeline event_queue.
    Used for broadcasting via WebSockets.
    """
    loop = asyncio.get_event_loop()
    while pipeline_running:
        # Use run_in_executor to fetch from synchronous queue without blocking event loop
        try:
            event = await loop.run_in_executor(None, lambda: event_queue.get(timeout=0.5))
            yield event
        except queue.Empty:
            continue
