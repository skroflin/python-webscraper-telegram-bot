import json
import logging
import os
import re
import urllib.request
from typing import Dict, Optional


def extract_features(title: str = "", description: str = "") -> dict:
    """
    Robust rule-based extractor for listing features, utilities, deposits and restrictions.
    Fast, local, and requires zero external API keys.
    """
    text = f"{title or ''} {description or ''}".lower()

    # --- Pet preferences ---
    has_pets_negative = any(re.search(pattern, text) for pattern in [
        r"bez\s+(kućnih\s+)?ljubimaca",
        r"ljubimci\s+nisu",
        r"nisu\s+dozvoljeni\s+ljubimci",
        r"no\s+pets",
        r"zabranjen[oi]\s+(za\s+)?ljubimce",
        r"kućni\s+ljubimci\s+isključeni"
    ])
    has_pets_positive = any(re.search(pattern, text) for pattern in [
        r"ljubimac", r"ljubimci", r"pas", r"mačka", r"macka", r"pets", r"pet\s*friendly", r"dozvoljeni\s+ljubimci"
    ])
    pet_friendly = has_pets_positive and not has_pets_negative

    # --- Parking ---
    parking = any(re.search(pattern, text) for pattern in [
        r"parking", r"garaž", r"garaz", r"parkirn", r"parkirno\s+mjesto"
    ])

    # --- Balcony / Terrace ---
    balcony = any(re.search(pattern, text) for pattern in [
        r"balkon", r"teras", r"lođ", r"lodj"
    ])

    # --- Heating ---
    heating = any(re.search(pattern, text) for pattern in [
        r"etažn", r"etazn", r"toplana", r"gradsko\s+grijanje", r"plinsko", r"dizalica\s+topline"
    ])

    # --- Elevator ---
    has_elevator_negative = any(re.search(pattern, text) for pattern in [
        r"nema\s+lift", r"bez\s+lifta", r"nema\s+dizalo", r"zgrada\s+nema\s+lift"
    ])
    has_elevator_positive = any(re.search(pattern, text) for pattern in [
        r"lift", r"dizal", r"ima\s+lift", r"zgrada\s+s\s+liftom"
    ])
    elevator = has_elevator_positive and not has_elevator_negative

    # --- Utilities (Režije) ---
    utilities_included = any(re.search(pattern, text) for pattern in [
        r"režije\s+(su\s+)?u\s+cijeni",
        r"režije\s+uključene",
        r"uključene\s+režije",
        r"sve\s+režije\s+u\s+cijeni",
        r"sa\s+režijama",
        r"režije\s+uračunate",
        r"cijena\s+s\s+režijama"
    ])

    utilities_separate = any(re.search(pattern, text) for pattern in [
        r"režije\s+posebno",
        r"plus\s+režije",
        r"\+\s*režije",
        r"režije\s+nisu\s+u\s+cijeni",
        r"plaćaju\s+se\s+režije",
        r"režije\s+po\s+potrošnji"
    ])

    utilities_est = None
    if not utilities_included:
        # Match patterns like: "režije cca 60-80 €", "režije oko 70 EUR", "režije fiksno 50e"
        est_match = re.search(
            r"režij[ea]\s*(?:su|se)?\s*(?:cca|oko|fiksno|prosječno)?\s*(\d{2,3}(?:\s*-\s*\d{2,3})?)\s*(?:€|eur|e\b)",
            text
        )
        if est_match:
            utilities_est = f"cca {est_match.group(1)} €"

    # --- Deposit (Polog / Jamčevina) ---
    deposit = None
    if re.search(r"bez\s+pologa|nema\s+pologa|polog\s+nije\s+potreban", text):
        deposit = "Bez pologa"
    elif re.search(r"polog\s*(u\s*visini)?\s*(jedne|1)\s*(mjesečne|najamnine|stanarine)", text):
        deposit = "1 mjesečna najamnina"
    elif re.search(r"polog\s*(u\s*visini)?\s*(dvije|2)\s*(mjesečne|najamnine|stanarine)", text):
        deposit = "2 mjesečne najamnine"
    else:
        dep_amount_match = re.search(
            r"polog\s*(?:iznosi|u\s*iznosu\s*od)?\s*(\d{2,4})\s*(?:€|eur|e\b)",
            text
        )
        if dep_amount_match:
            deposit = f"{dep_amount_match.group(1)} €"
        elif "polog" in text or "jamčevin" in text or "depozit" in text:
            deposit = "Obavezan (iznos u opisu)"

    # --- Restrictions / Conditions ---
    non_smokers = any(re.search(pattern, text) for pattern in [
        r"nepušač", r"nepusac", r"zabranjeno\s+pušenje", r"samo\s+nepušači"
    ])

    contract_required = any(re.search(pattern, text) for pattern in [
        r"ugovor\s+(o\s+najmu\s+)?obavezan",
        r"obavezna\s+prijava",
        r"prijava\s+i\s+ugovor",
        r"solemnizacija"
    ])

    students_welcome = any(re.search(pattern, text) for pattern in [
        r"prednost\s+student", r"studenti(ma)?\s+dobrodošli", r"idealno\s+za\s+studente"
    ])

    return {
        "pet_friendly": pet_friendly,
        "pet_prohibited": has_pets_negative,
        "parking": parking,
        "balcony": balcony,
        "heating": heating,
        "elevator": elevator,
        "elevator_negative": has_elevator_negative,
        "utilities_included": utilities_included,
        "utilities_separate": utilities_separate,
        "utilities_est": utilities_est,
        "deposit": deposit,
        "non_smokers": non_smokers,
        "contract_required": contract_required,
        "students_welcome": students_welcome,
    }


def extract_features_with_ai(
    title: str = "",
    description: str = "",
    api_key: Optional[str] = None
) -> dict:
    """
    Enhanced extraction utilizing Google Gemini API for deep linguistic analysis
    of subtle lease conditions, utility breakdowns, and concise TL;DR summarization.
    Gracefully falls back to extract_features() if no API key or upon network failure.
    """
    base_features = extract_features(title, description)

    api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return base_features

    raw_text = f"Naslov: {title}\nOpis: {description}"
    if len(raw_text.strip()) < 30:
        return base_features

    prompt = f"""Ti si analitičar oglasa za najam nekretnina u Osijeku. Iz teksta oglasa izvuci točne podatke u JSON formatu:
Tekst oglasa:
{raw_text}

Odgovori isključivo sa sljedećim JSON formatom (bez markdown koda i bez komentara):
{{
  "utilities_included": true/false,
  "utilities_estimate": "cca 60-80 €" ili null,
  "deposit": "1 najamnina" ili "300 €" ili "bez pologa" ili null,
  "pet_friendly": true/false,
  "non_smokers": true/false,
  "elevator": true/false,
  "parking": true/false,
  "summary": "Maksimalno 15 riječi sažetka ključnih prednosti stana."
}}
"""
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

        with urllib.request.urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            candidate_text = result["candidates"][0]["content"]["parts"][0]["text"]
            ai_data = json.loads(candidate_text)

            # Merge AI insights with rule-based features
            if ai_data.get("utilities_included") is not None:
                base_features["utilities_included"] = bool(ai_data["utilities_included"])
            if ai_data.get("utilities_estimate"):
                base_features["utilities_est"] = str(ai_data["utilities_estimate"])
            if ai_data.get("deposit"):
                base_features["deposit"] = str(ai_data["deposit"])
            if ai_data.get("summary"):
                base_features["ai_summary"] = str(ai_data["summary"])
            if ai_data.get("non_smokers") is not None:
                base_features["non_smokers"] = bool(ai_data["non_smokers"])

    except Exception as e:
        logging.warning("AI extraction fallback to rule-based parser: %s", e)

    return base_features


def format_feature_badges(title: str = "", description: str = "", use_ai: bool = False) -> str:
    """
    Formats extracted apartment characteristics into clean Telegram markdown badges,
    including financial details (utilities, deposit) and tenant conditions.
    """
    features = extract_features_with_ai(title, description) if use_ai else extract_features(title, description)
    badges = []

    # Financial details
    if features.get("utilities_included"):
        badges.append("- 💡 **Režije:** Uključene u cijenu najma\n")
    elif features.get("utilities_est"):
        badges.append(f"- 💡 **Režije:** {features['utilities_est']}\n")
    elif features.get("utilities_separate"):
        badges.append("- 💡 **Režije:** Nisu u cijeni (plaćaju se posebno)\n")

    if features.get("deposit"):
        badges.append(f"- 🔒 **Polog:** {features['deposit']}\n")

    # Property amenities
    if features.get("pet_friendly"):
        badges.append("- 🐾 Pet friendly\n")
    if features.get("parking"):
        badges.append("- 🅿️ Parking / Garaža\n")
    if features.get("elevator"):
        badges.append("- 🛗 Lift\n")
    if features.get("balcony"):
        badges.append("- 🌅 Balkon / Terasa\n")
    if features.get("heating"):
        badges.append("- ♨️ Etažno / Gradsko grijanje\n")

    # Conditions & AI Summary
    if features.get("non_smokers"):
        badges.append("- 🚭 Isključivo nepušači\n")
    if features.get("contract_required"):
        badges.append("- 📄 Ugovor o najmu obavezan\n")

    if features.get("ai_summary"):
        badges.append(f"\n💡 *AI Sažetak:* _{features['ai_summary']}_\n")

    if not badges:
        return ""

    return f"✨ **Detalji i uvjeti:**\n{''.join(badges)}"
