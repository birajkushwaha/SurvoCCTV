import uuid
from datetime import datetime
from backend.app import database

# Keep track of active state for rate limiting alerts
# format: {camera_id: {anomaly_type: last_trigger_timestamp}}
_last_triggered = {}

# Keep track of track history for fall and loitering detection
# format: {track_id: {"first_seen": datetime, "last_seen": datetime, "history": [(w, h, x, y)]}}
_track_states = {}

def check_queue_overflow(camera_id, queue_zone_name, current_queue_count):
    """
    Checks if the queue queue exceeds the threshold (e.g., 4 people).
    Triggers an anomaly alert, rate-limited to once every 60 seconds.
    """
    threshold = 4
    if current_queue_count > threshold:
        anomaly_type = "queue_overflow"
        now = datetime.now()
        
        # Check rate limit
        last_triggered_time = _last_triggered.get(camera_id, {}).get(anomaly_type)
        if last_triggered_time and (now - last_triggered_time).total_seconds() < 60:
            return None
            
        # Register trigger
        if camera_id not in _last_triggered:
            _last_triggered[camera_id] = {}
        _last_triggered[camera_id][anomaly_type] = now
        
        anomaly_id = str(uuid.uuid4())
        timestamp = now.isoformat()
        desc = f"Queue overflow detected at {queue_zone_name.replace('_', ' ').title()}. Current size: {current_queue_count} people (limit: {threshold})."
        
        database.save_anomaly(anomaly_id, timestamp, camera_id, None, anomaly_type, desc)
        
        # Save as standard event too
        database.save_event(
            event_id=str(uuid.uuid4()),
            timestamp=timestamp,
            camera_id=camera_id,
            track_id=None,
            event_type="anomaly",
            zone=queue_zone_name,
            payload_dict={"anomaly_id": anomaly_id, "anomaly_type": anomaly_type, "description": desc, "queue_size": current_queue_count}
        )
        return {
            "anomaly_id": anomaly_id,
            "timestamp": timestamp,
            "camera_id": camera_id,
            "anomaly_type": anomaly_type,
            "description": desc
        }
    return None

def update_track_state_and_check(camera_id, track_id, zone, bbox):
    """
    Updates the historical coordinates and dimensions of a person track.
    Checks for loitering (> 40s in shelves) and falls (aspect ratio changes).
    bbox format: (x_center, y_center, w, h)
    """
    now = datetime.now()
    x, y, w, h = bbox
    
    if track_id not in _track_states:
        _track_states[track_id] = {
            "first_seen": now,
            "last_seen": now,
            "zone": zone,
            "history": [(w, h, x, y)],
            "anomalies_triggered": set()
        }
    else:
        state = _track_states[track_id]
        state["last_seen"] = now
        state["history"].append((w, h, x, y))
        # Limit history length to last 50 frames
        if len(state["history"]) > 50:
            state["history"].pop(0)
            
    state = _track_states[track_id]
    
    # 1. Fall Detection Check
    # If height was much larger than width, but now width is larger than height, and bbox center is low.
    # E.g. h/w was > 1.5, now h/w is < 0.75 and width is significant.
    if "customer_fall" not in state["anomalies_triggered"] and len(state["history"]) > 5:
        # Check historical aspect ratio (first few frames)
        aspects = [h_hist / w_hist for w_hist, h_hist, _, _ in state["history"][:5] if w_hist > 0]
        current_aspect = h / w if w > 0 else 1.0
        
        # If they were standing (aspect > 1.5) and now lying down (aspect < 0.8)
        was_standing = any(a > 1.5 for a in aspects)
        is_flat = current_aspect < 0.8
        
        if was_standing and is_flat:
            state["anomalies_triggered"].add("customer_fall")
            
            anomaly_id = str(uuid.uuid4())
            timestamp = now.isoformat()
            desc = f"Customer fall detected in zone {zone.replace('_', ' ').title()} (Track ID: {track_id}). BBox aspect ratio fell to {current_aspect:.2f}."
            
            database.save_anomaly(anomaly_id, timestamp, camera_id, track_id, "customer_fall", desc)
            database.save_event(
                event_id=str(uuid.uuid4()),
                timestamp=timestamp,
                camera_id=camera_id,
                track_id=track_id,
                event_type="anomaly",
                zone=zone,
                payload_dict={"anomaly_id": anomaly_id, "anomaly_type": "customer_fall", "description": desc}
            )
            return {
                "anomaly_id": anomaly_id,
                "timestamp": timestamp,
                "camera_id": camera_id,
                "track_id": track_id,
                "anomaly_type": "customer_fall",
                "description": desc
            }
            
    # 2. Loitering Check
    # If track has been in a shelf zone for > 40 seconds
    if "shelves" in zone and "loitering" not in state["anomalies_triggered"]:
        dwell_seconds = (now - state["first_seen"]).total_seconds()
        if dwell_seconds > 40:
            state["anomalies_triggered"].add("loitering")
            
            anomaly_id = str(uuid.uuid4())
            timestamp = now.isoformat()
            desc = f"Loitering alert: customer (Track ID: {track_id}) has spent {dwell_seconds:.0f} seconds in the product shelves zone."
            
            database.save_anomaly(anomaly_id, timestamp, camera_id, track_id, "loitering", desc)
            database.save_event(
                event_id=str(uuid.uuid4()),
                timestamp=timestamp,
                camera_id=camera_id,
                track_id=track_id,
                event_type="anomaly",
                zone=zone,
                payload_dict={"anomaly_id": anomaly_id, "anomaly_type": "loitering", "description": desc, "dwell_seconds": dwell_seconds}
            )
            return {
                "anomaly_id": anomaly_id,
                "timestamp": timestamp,
                "camera_id": camera_id,
                "track_id": track_id,
                "anomaly_type": "loitering",
                "description": desc
            }
            
    return None

def clean_stale_tracks(max_age_seconds=30):
    """
    Cleans tracks that haven't been seen recently from memory.
    """
    now = datetime.now()
    to_delete = []
    for track_id, state in _track_states.items():
        if (now - state["last_seen"]).total_seconds() > max_age_seconds:
            to_delete.append(track_id)
            
    for track_id in to_delete:
        del _track_states[track_id]
