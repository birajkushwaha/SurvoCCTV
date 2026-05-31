from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class StoreEvent(BaseModel):
    event_id: str = Field(..., description="Unique event identifier (UUID)")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    camera_id: str = Field(..., description="Camera ID that captured the event")
    track_id: Optional[int] = Field(None, description="Tracking ID of the person")
    event_type: str = Field(..., description="Type of event: entry, exit, dwell, queue_entry, etc.")
    zone: Optional[str] = Field(None, description="Store zone name")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary for event details")

class StoreAnomaly(BaseModel):
    anomaly_id: str = Field(..., description="Unique anomaly identifier (UUID)")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    camera_id: str = Field(..., description="Camera ID where anomaly was detected")
    track_id: Optional[int] = Field(None, description="Track ID of the person associated with anomaly")
    anomaly_type: str = Field(..., description="Type: loitering, queue_overflow, customer_fall, after_hours")
    description: str = Field(..., description="Human readable details")
    status: str = Field("active", description="Status: active or resolved")

class CameraInfo(BaseModel):
    camera_id: str
    name: str
    status: str  # online, offline, processing
    fps: float
    resolution: str
    current_occupancy: int

class StoreMetrics(BaseModel):
    total_customers: int = Field(..., description="Total customers seen today")
    avg_dwell_seconds: float = Field(..., description="Average time spent in the store in seconds")
    active_anomalies: int = Field(..., description="Number of unresolved anomalies")
    current_occupancy: int = Field(..., description="Total count of people currently inside the store")
    queue_lengths: Dict[str, int] = Field(..., description="Map of cashier ID to current queue length")

class HistoricalOccupancy(BaseModel):
    timestamp: str
    occupancy: int
