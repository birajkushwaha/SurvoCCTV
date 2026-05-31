import cv2
import numpy as np

# Spatial zones defined as polygons [[x1, y1], [x2, y2], ...] on 1920x1080 frames.
ZONES = {
    "CAM 1": {
        "entrance": np.array([[50, 400], [500, 400], [500, 1050], [50, 1050]], dtype=np.int32),
        "exit": np.array([[500, 400], [950, 400], [950, 1050], [500, 1050]], dtype=np.int32),
        "store_floor": np.array([[950, 100], [1900, 100], [1900, 1050], [950, 1050]], dtype=np.int32)
    },
    "CAM 2": {
        "aisle_1_shelves": np.array([[100, 200], [800, 200], [800, 950], [100, 950]], dtype=np.int32),
        "aisle_1_pathway": np.array([[800, 100], [1800, 100], [1800, 1050], [800, 1050]], dtype=np.int32)
    },
    "CAM 3": {
        "aisle_2_shelves": np.array([[100, 200], [800, 200], [800, 950], [100, 950]], dtype=np.int32),
        "aisle_2_pathway": np.array([[800, 100], [1800, 100], [1800, 1050], [800, 1050]], dtype=np.int32)
    },
    "CAM 4": {
        "cashier_queue_1": np.array([[200, 300], [1100, 300], [1100, 900], [200, 900]], dtype=np.int32),
        "cashier_desk_1": np.array([[1100, 200], [1750, 200], [1750, 850], [1100, 850]], dtype=np.int32)
    },
    "CAM 5": {
        "cashier_queue_2": np.array([[200, 300], [1100, 300], [1100, 900], [200, 900]], dtype=np.int32),
        "cashier_desk_2": np.array([[1100, 200], [1750, 200], [1750, 850], [1100, 850]], dtype=np.int32)
    }
}

# Color mapping for visualization (BGR format)
ZONE_COLORS = {
    "entrance": (0, 255, 0),         # Green
    "exit": (0, 0, 255),             # Red
    "store_floor": (255, 255, 0),     # Cyan
    "aisle_1_shelves": (255, 0, 255), # Magenta
    "aisle_1_pathway": (255, 128, 0), # Orange
    "aisle_2_shelves": (255, 0, 255), # Magenta
    "aisle_2_pathway": (255, 128, 0), # Orange
    "cashier_queue_1": (0, 165, 255),# Gold/Orange
    "cashier_desk_1": (0, 255, 255), # Yellow
    "cashier_queue_2": (0, 165, 255),# Gold/Orange
    "cashier_desk_2": (0, 255, 255)  # Yellow
}

def get_zone_at_point(camera_id, x, y):
    """
    Returns the zone name if the point (x, y) is inside any defined zone for a camera.
    Returns 'general' if the point is inside the frame but not in any specific zone.
    """
    camera_zones = ZONES.get(camera_id, {})
    for zone_name, polygon in camera_zones.items():
        # cv2.pointPolygonTest returns positive value if inside, negative if outside, 0 if on edge
        res = cv2.pointPolygonTest(polygon, (float(x), float(y)), False)
        if res >= 0:
            return zone_name
    return "general"

def draw_zones_on_frame(camera_id, frame):
    """
    Draws semi-transparent zone polygons and text overlays on the video frame.
    """
    camera_zones = ZONES.get(camera_id, {})
    overlay = frame.copy()
    
    for zone_name, polygon in camera_zones.items():
        color = ZONE_COLORS.get(zone_name, (200, 200, 200))
        # Draw transparent filled polygon
        cv2.fillPoly(overlay, [polygon], color)
        # Draw polygon boundary
        cv2.polylines(frame, [polygon], True, color, 2)
        
        # Draw zone label text near the first point of the polygon
        text_pos = tuple(polygon[0])
        cv2.putText(
            frame, 
            zone_name.replace("_", " ").title(), 
            (text_pos[0], text_pos[1] - 10), 
            cv2.FONT_HERSHEY_SIMPLEX, 
            0.6, 
            color, 
            2, 
            cv2.LINE_AA
        )
        
    # Alpha blend overlay with original frame to make polygons semi-transparent
    alpha = 0.2
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)
    return frame
