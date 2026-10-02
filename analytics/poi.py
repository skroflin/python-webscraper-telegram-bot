import math
from typing import Dict, List, Optional

OSIJEK_POI = {
    "portanova": {"name": "TC Portanova", "category": "shopping", "lat": 45.5615, "lon": 18.6280},
    "mall_osijek": {"name": "Mall Osijek", "category": "shopping", "lat": 45.5418, "lon": 18.7088},
    "konzum_super_svacicova": {"name": "Super Konzum (Svačićeva)", "category": "supermarket", "lat": 45.5528, "lon": 18.6945},
    "konzum_centar": {"name": "Konzum Centar (Trg)", "category": "supermarket", "lat": 45.5605, "lon": 18.6792},
    "konzum_retfala": {"name": "Konzum (Retfala / Strossmayerova)", "category": "supermarket", "lat": 45.5618, "lon": 18.6520},
    "interspar_dakovstina": {"name": "Interspar (Đakovština)", "category": "supermarket", "lat": 45.5525, "lon": 18.6705},
    "interspar_retfala": {"name": "Interspar (Retfala)", "category": "supermarket", "lat": 45.5622, "lon": 18.6435},
    "lidl_retfala": {"name": "Lidl (Retfala)", "category": "supermarket", "lat": 45.5620, "lon": 18.6410},
    "lidl_svacicova": {"name": "Lidl (Svačićeva / Kampus)", "category": "supermarket", "lat": 45.5515, "lon": 18.6990},
    "lidl_donji_grad": {"name": "Lidl (Donji Grad)", "category": "supermarket", "lat": 45.5565, "lon": 18.7250},
    "kaufland_retfala": {"name": "Kaufland (Retfala)", "category": "supermarket", "lat": 45.5625, "lon": 18.6480},
    "eurospin_gacka": {"name": "Eurospin (Gacka)", "category": "supermarket", "lat": 45.5450, "lon": 18.6930},
    "plodine_huttlerova": {"name": "Plodine (Huttlerova)", "category": "supermarket", "lat": 45.5505, "lon": 18.7180},
    "kbc_bolnica": {"name": "KBC Osijek (Bolnica)", "category": "health", "lat": 45.5582, "lon": 18.7115},
    "dom_zdravlja_centar": {"name": "Dom zdravlja Centar", "category": "health", "lat": 45.5590, "lon": 18.6870},
    "dom_zdravlja_retfala": {"name": "Dom zdravlja Retfala", "category": "health", "lat": 45.5610, "lon": 18.6490},
    "dom_zdravlja_donji_grad": {"name": "Dom zdravlja Donji Grad", "category": "health", "lat": 45.5595, "lon": 18.7220},
    "dom_zdravlja_jug2": {"name": "Dom zdravlja Jug 2", "category": "health", "lat": 45.5410, "lon": 18.7140},
    "dom_zdravlja_industrial": {"name": "Dom zdravlja Industrijska", "category": "health", "lat": 45.5435, "lon": 18.6770},
    "kampus_faks": {"name": "Sveučilišni kampus", "category": "education", "lat": 45.5542, "lon": 18.7032},
    "ffos": {"name": "Filozofski fakultet (FFOS)", "category": "education", "lat": 45.5574, "lon": 18.6806},
    "efos": {"name": "Ekonomski fakultet (EFOS)", "category": "education", "lat": 45.5570, "lon": 18.6850},
    "pravos": {"name": "Pravni fakultet (PRAVOS)", "category": "education", "lat": 45.5560, "lon": 18.6810},
    "ferit_trpimirova": {"name": "FERIT (Trpimirova)", "category": "education", "lat": 45.5535, "lon": 18.7025},
    "mefos": {"name": "Medicinski fakultet (MEFOS)", "category": "education", "lat": 45.5585, "lon": 18.7120},
    "gradnos": {"name": "Građevinski i arhitektonski (GRADNOS)", "category": "education", "lat": 45.5540, "lon": 18.7040},
    "autobusni_kolodvor": {"name": "Autobusni kolodvor", "category": "transport", "lat": 45.5528, "lon": 18.6758},
    "zeljeznicki_kolodvor": {"name": "Željeznički kolodvor", "category": "transport", "lat": 45.5522, "lon": 18.6765},
    "centar_trg": {"name": "Trg Ante Starčevića", "category": "landmark", "lat": 45.5601, "lon": 18.6789},
    "tvrda": {"name": "Tvrđa", "category": "landmark", "lat": 45.5610, "lon": 18.6960},
    "opus_arena": {"name": "Opus Arena (Pampas)", "category": "sports", "lat": 45.5650, "lon": 18.6380},
    "gradski_vrt": {"name": "Dvorana / Stadion Gradski vrt", "category": "sports", "lat": 45.5445, "lon": 18.6970},
    "copacabana": {"name": "Copacabana (Kopa)", "category": "recreation", "lat": 45.5670, "lon": 18.6820},
}


def calculate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def get_nearest_pois(lat: float, lon: float, limit_per_category: int = 1) -> Dict[str, List[dict]]:
    categorized: Dict[str, List[dict]] = {}

    for poi_id, info in OSIJEK_POI.items():
        dist_km = calculate_distance_km(lat, lon, info["lat"], info["lon"])
        cat = info.get("category", "other")

        item = {
            "id": poi_id,
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


def format_poi_distances(lat: Optional[float], lon: Optional[float]) -> str:
    if not lat or not lon:
        return ""

    nearest = get_nearest_pois(lat, lon, limit_per_category=1)
    lines = []

    cat_labels = {
        "health": "\U0001F3E5 Zdravstvo",
        "supermarket": "\U0001F6D2 Trgovina",
        "education": "\U0001F393 Faks / Kampus",
        "shopping": "\U0001F3EC TC / Shopping",
        "transport": "\U0001F68C Kolodvor"
    }

    for cat_key, label in cat_labels.items():
        if cat_key in nearest and nearest[cat_key]:
            poi = nearest[cat_key][0]
            lines.append(f"  • {label}: **{poi['name']}** (~{poi['formatted_distance']})")

    if not lines:
        return ""

    return "\U0001F3EB **Blizina sadržaja:**\n" + "\n".join(lines) + "\n\n"