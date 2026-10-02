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
        r"parking", r"garaža", r"garaza", r"garažno", r"garazno", r"parkirn"
    ])

    balcony = any(re.search(pattern, text) for pattern in [
        r"balkon", r"terasa", r"lođa", r"lodja"
    ])

    heating = any(re.search(pattern, text) for pattern in [
        r"etažno", r"etazno", r"toplana", r"gradsko\s+grijanje", r"plinsko"
    ])

    return {
        "pet_friendly": pet_friendly,
        "parking": parking,
        "balcony": balcony,
        "heating": heating
    }


def format_feature_badges(title: str = "", description: str = "") -> str:
    features = extract_features(title, description)
    badges = []

    if features["pet_friendly"]:
        badges.append("\U0001F436 Pet friendly")
    if features["parking"]:
        badges.append("\U0001F17F\ufe0f Parking")
    if features["balcony"]:
        badges.append("\U0001F305 Balkon / Terasa")
    if features["heating"]:
        badges.append("\u2668\ufe0f Etažno / Gradsko grijanje")

    if not badges:
        return ""

    return f"\U00002728 **Značajke:** { ' | '.join(badges) }\n\n"