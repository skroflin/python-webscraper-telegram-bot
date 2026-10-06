import math
from typing import Dict, List, Optional
from database.database import get_connectivity


def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_all_pois_from_db() -> List[dict]:
    try:
        with get_connectivity() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key_name, name, category, latitude, longitude FROM pois")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        return []


def get_nearest_pois(
    lat: float,
    lon: float,
    limit_per_category: int = 1,
    pois: Optional[List[dict]] = None,
) -> Dict[str, List[dict]]:
    pois = get_all_pois_from_db() if pois is None else pois
    categorized: Dict[str, List[dict]] = {}

    for info in pois:
        dist_km = calculate_distance_km(lat, lon, info["latitude"], info["longitude"])
        cat = info.get("category", "other")

        item = {
            "id": info["key_name"],
            "name": info["name"],
            "distance_km": dist_km,
            "formatted_distance": f"{int(dist_km * 1000)} m" if dist_km < 1.0 else f"{dist_km:.1f} km"
        }

        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(item)

    result = {}
    for cat, items in categorized.items():
        items.sort(key=lambda x: x["distance_km"])
        result[cat] = items[:limit_per_category]

    return result


def format_poi_distances(
    lat: Optional[float], lon: Optional[float], pois: Optional[List[dict]] = None
) -> str:
    if lat is None or lon is None:
        return ""

    nearest = get_nearest_pois(lat, lon, limit_per_category=1, pois=pois)
    lines = []

    cat_labels = {
        "health": "- \U0001F3E5 Zdravstvo",
        "supermarket": "- \U0001F6D2 Trgovina",
        "education": "- \U0001F393 Faks / Kampus",
        "shopping": "- \U0001F3EC TC / Shopping",
        "transport": "- \U0001F68C Kolodvor"
    }

    for cat_key, label in cat_labels.items():
        if cat_key in nearest and nearest[cat_key]:
            poi = nearest[cat_key][0]
            lines.append(f"{label}: **{poi['name']}** (~{poi['formatted_distance']})")

    if not lines:
        return ""

    return "\U0001F3EB **Blizina objekta:**\n" + "\n".join(lines) + "\n\n"