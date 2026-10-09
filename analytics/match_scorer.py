from typing import Optional, List, Tuple
from analytics.feature_extractor import extract_features
from analytics.poi import get_nearest_pois


def calculate_match_score(
    listing: dict, 
    user_profile: Optional[dict] = None, 
    user_location_ids: Optional[List[int]] = None,
    pois: Optional[List[dict]] = None,
) -> Tuple[int, List[str]]:
    score = 0
    reasons = []

    user_profile = user_profile or {}
    user_location_ids = user_location_ids or []

    listing_loc_id = listing.get("location_id")
    if user_location_ids and listing_loc_id in user_location_ids:
        score += 20
        reasons.append("\u2705 U vašem odabranom kvartu")
    elif not user_location_ids:
        score += 10

    price = listing.get("price", 0)
    max_price = user_profile.get("max_price")
    if max_price:
        if price <= max_price:
            score += 10
            reasons.append(f"\u2705 Unutar budžeta (\u2264 {max_price:.0f} \u20ac)")
        else:
            diff = price - max_price
            score -= 10
            reasons.append(f"\u26a0\ufe0f Iznad budžeta (+{diff:.0f} \u20ac)")
    else:
        score += 10

    min_area = user_profile.get("min_area")
    area = listing.get("area_sqm")
    if min_area:
        if area is None:
            reasons.append("\u26a0\ufe0f Kvadratura nije navedena")
        elif area >= min_area:
            score += 10
            reasons.append(f"\u2705 Odgovara min. površini (\u2265 {min_area:.0f} m\u00b2)")
    else:
        score += 10

    features = extract_features(listing.get("title", ""), listing.get("description", ""))
    feature_points = 0

    must_have_lift = user_profile.get("must_have_lift", 0)
    must_have_pet = user_profile.get("must_have_pet", 0)
    must_have_parking = user_profile.get("must_have_parking", 0)

    # Elevator
    if must_have_lift:
        if features.get("elevator"):
            feature_points += 15
            reasons.append("\U0001f6d7 Zgrada ima lift (traženo)")
        elif features.get("elevator_negative"):
            feature_points -= 20
            reasons.append("\u274c Zgrada NEMA lift")
        else:
            feature_points -= 5
            reasons.append("\u26a0\ufe0f Lift nije naveden")
    elif features.get("elevator"):
        feature_points += 8
        reasons.append("\U0001f6d7 Zgrada ima lift")

    # Pets
    if must_have_pet:
        if features.get("pet_friendly"):
            feature_points += 15
            reasons.append("\U0001f436 Pet friendly (traženo)")
        elif features.get("pet_prohibited"):
            feature_points -= 30
            reasons.append("\u274c Kućni ljubimci NISU dozvoljeni")
        else:
            feature_points -= 5
            reasons.append("\u26a0\ufe0f Dozvoljenost ljubimaca nije navedena")
    elif features.get("pet_friendly"):
        feature_points += 8
        reasons.append("\U0001f436 Pet friendly")

    # Parking
    if must_have_parking:
        if features.get("parking"):
            feature_points += 15
            reasons.append("\U0001f17f\ufe0f Parking / Garaža (traženo)")
        else:
            feature_points -= 10
            reasons.append("\u26a0\ufe0f Parking / garaža nije navedena")
    elif features.get("parking"):
        feature_points += 7
        reasons.append("\U0001f17f\ufe0f Parking / Garaža")

    # Balcony
    if features.get("balcony"):
        feature_points += 7
        reasons.append("\U0001f305 Balkon / Terasa")

    score += max(-30, min(feature_points, 35))

    lat, lon = listing.get("latitude"), listing.get("longitude")
    if lat is not None and lon is not None:
        nearest = get_nearest_pois(lat, lon, limit_per_category=1, pois=pois)
        all_distances = [
            items[0]["distance_km"] 
            for items in nearest.values() 
            if items
        ]
        if all_distances:
            min_dist = min(all_distances)
            if min_dist <= 0.5:
                score += 30
                reasons.append("\U0001f3eb Izvrsna mikrolokacija (< 500m do sadržaja)")
            elif min_dist <= 1.2:
                score += 20
                reasons.append("\U0001f3eb Dobra lokacija (< 1.2km do sadržaja)")
            elif min_dist <= 2.5:
                score += 10
            else:
                score += 5

    final_score = max(0, min(100, score))
    return final_score, reasons


def get_match_badge(score: int) -> str:
    if score >= 85:
        return f"\U0001f3af **Match: {score}%** (\u2b50 Top prilika)"
    elif score >= 65:
        return f"\U0001f3af **Match: {score}%** (\U0001f44d Vrlo dobro)"
    elif score >= 45:
        return f"\U0001f3af **Match: {score}%** (\u2139\ufe0f Solidno)"
    else:
        return f"\U0001f3af **Match: {score}%**"