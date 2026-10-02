import re


def extract_features(title: str = "", description: str = "") -> dict:
    text = f"{title or ''} {description or ''}".lower()

    has_pets_negative = any(re.search(pattern, text) for pattern in [
        r"bez\s+(kućnih\s+)?ljubimaca",
        r"ljubimci\s+nisu",
        r"nisu\s+dozvoljeni\s+ljubimci",
        r"no\s+pets",
        r"zabranjen[oi]\s+(za\s+)?ljubimce"
    ])
    has_pets_positive = any(re.search(pattern, text) for pattern in [
        r"ljubimac", r"ljubimci", r"pas", r"mačka", r"macka", r"pets", r"pet\s*friendly"
    ])
    pet_friendly = has_pets_positive and not has_pets_negative

    parking = any(re.search(pattern, text) for pattern in [
        r"parking", r"garaž", r"garaz", r"parkirn"
    ])
    
    balcony = any(re.search(pattern, text) for pattern in [
        r"balkon", r"teras", r"lođ", r"lodj"
    ])
    
    heating = any(re.search(pattern, text) for pattern in [
        r"etažn", r"etazn", r"toplana", r"gradsko\s+grijanje", r"plinsko"
    ])
    
    has_elevator_negative = any(re.search(pattern, text) for pattern in [
        r"nema\s+lift", r"bez\s+lifta", r"nema\s+dizalo"
    ])
    
    has_elevator_positive = any(re.search(pattern, text) for pattern in [
        r"lift", r"dizal", r"ima\s+lift"
    ])
    elevator = has_elevator_positive and not has_elevator_negative

    return {
        "pet_friendly": pet_friendly,
        "parking": parking,
        "balcony": balcony,
        "heating": heating,
        "elevator": elevator
    }


def format_feature_badges(title: str = "", description: str = "") -> str:
    features = extract_features(title, description)
    badges = []

    if features["pet_friendly"]:
        badges.append("\U0001F436 Pet friendly")
    if features["parking"]:
        badges.append("\U0001F17F\ufe0f Parking / Garaža")
    if features["balcony"]:
        badges.append("\U0001F305 Balkon / Terasa")
    if features["heating"]:
        badges.append("\u2668\ufe0f Etažno / Gradsko grijanje")
    if features["elevator"]:
        badges.append("\U0001F6D7 Lift")

    if not badges:
        return ""

    return f"\u2728 **Značajke:** {' | '.join(badges)}\n"