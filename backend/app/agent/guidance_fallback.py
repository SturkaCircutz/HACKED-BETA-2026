"""Conservative Edmonton guidance if the optional AI planning workflow cannot complete."""
from __future__ import annotations

import re

CITY_311 = "https://311.edmonton.ca/"
CITY_GUIDANCE = "https://www.edmonton.ca/programs_services/311-city-services"
CITY_SORTING = "https://www.edmonton.ca/programs_services/garbage_waste/waste-sorting-public-space"
CITY_LITTER = "https://www.edmonton.ca/programs_services/garbage_waste/managing-your-waste-public"


def fallback_guidance(state: dict) -> dict:
    story = str(state.get("story") or state.get("issue_summary") or "")
    text = story.casefold()
    text = re.sub(r"\b(?:no|without)\s+(?:any\s+)?(?:needles?|syringes?|broken glass|chemicals?)\b", "", text)
    jurisdiction_id = str(state.get("jurisdiction_id") or "").casefold()
    city = str(state.get("city") or "").casefold()
    address = str(state.get("address") or "").casefold()
    inside = jurisdiction_id == "ca-ab-edmonton" or city == "edmonton" or "edmonton" in address
    outside = bool(jurisdiction_id) and not inside
    status = "inside" if inside else "outside" if outside else "unknown"

    def has(pattern: str) -> bool:
        return re.search(pattern, text) is not None

    emergency = has(r"\b(?:active fire|on fire|active flames?|gas leak|live (?:electric|electrical) wires?)\b")
    sharps = has(r"\b(?:needles?|syringes?|broken glass)\b")
    hazardous = has(r"\b(?:chemicals?|chemical spill|solvents?|oil spill|asbestos|propane|pesticides?)\b")
    bulky = has(r"\b(?:mattress(?:es)?|couch(?:es)?|sofa(?:s)?|furniture|fridge|refrigerator|large pile|illegal dumping)\b")
    overflowing = has(r"\b(?:overflowing|overflow|full garbage can|full trash bin)\b")
    source_category = str(state.get("category") or "other")
    if sharps:
        category = "needle"
    elif hazardous or emergency:
        category = "hazardous"
    elif bulky:
        category = "illegal_dumping"
    elif overflowing:
        category = "overflowing_bin"
    elif source_category in {"trash", "dumping", "litter"}:
        category = "illegal_dumping" if source_category == "dumping" else "litter"
    elif source_category in {"water", "air", "noise", "graffiti", "pothole", "tree"}:
        category = source_category
    else:
        category = "other"

    level = 5 if emergency else 4 if sharps or hazardous else 3 if bulky or category == "illegal_dumping" else 2 if category in {"overflowing_bin", "other"} else 1
    priority = "emergency" if emergency else "urgent" if level >= 4 else "routine"
    if emergency:
        steps = ["Keep away from the immediate danger; do not attempt cleanup.",
                 "Call 911 for an active emergency and describe the location."]
    elif sharps or hazardous:
        steps = ["Do not touch needles, broken glass, chemicals or unknown hazardous materials.",
                 "If safe, note the precise location and take a photo from a distance.",
                 "Contact the responsible municipal service using 311 if this is in Edmonton."]
    elif bulky:
        steps = ["Do not lift or move dumped furniture or oversized rubbish.",
                 "Note the location, approximate size and material; take a photo if safe.",
                 "Use Edmonton 311 to report illegal dumping on public property if this location is in Edmonton."]
    elif category == "litter":
        steps = ["Check for traffic, sharp objects and any unknown substances before handling the area.",
                 "If it is only a small amount of ordinary litter and you can safely handle it, collect it with suitable protective equipment.",
                 "Use the correct public bin or take it home for appropriate sorting; never leave bags beside a full bin.",
                 "For City help, open Edmonton 311 and select New Request > Litter/Waste > Litter Public Property (if applicable); include the location and a safe photo."]
    else:
        steps = ["Avoid touching or moving anything unsafe.",
                 "Record the location and details of the issue; photograph it only if safe.",
                 "If the location is in Edmonton, check the appropriate service category through Edmonton 311."]
    if status != "inside" and not emergency:
        steps.append("Confirm which municipality is responsible before using its 311 service.")

    risk_reason = "Text description only. No on-site safety or photo verification was completed."
    requires311 = False if emergency else None if status != "inside" else category not in {"litter"}
    if category == "litter" and status == "inside":
        requires311 = False
    if emergency:
        assistance = "Call emergency services instead of 311 for immediate danger."
    elif status != "inside":
        assistance = "Confirm the municipality before selecting a 311 service."
    elif requires311:
        assistance = "Request City assistance for unsafe, oversized or non-routine issues."
    else:
        assistance = "Edmonton 311 can accept public-litter reports, but assistance is optional for small, safely manageable litter."

    materials = []
    if has(r"\b(?:plastic bags?|coffee cups?|paper cups?|plastic bottles?|wrappers?)\b"):
        materials.append({"name": "Reported packaging materials", "sustainability_friendly": None,
                          "recyclable": None, "recycling_condition": "Material and condition must be checked using the public-bin signs and City WasteWise guidance; some coffee cups and plastic bags have container-specific rules.",
                          "source_url": CITY_SORTING})
    else:
        materials.append({"name": "Reported material", "sustainability_friendly": None,
                          "recyclable": None, "recycling_condition": "Recyclability cannot be verified from this description; consult City sorting guidance.",
                          "source_url": CITY_SORTING})

    phone = "911" if emergency else "311" if inside else None
    url = None if emergency else CITY_311 if inside or status == "unknown" else None
    report_text = (f"Location: {state.get('address') or f'{state.get('lat', '?')}, {state.get('lng', '?')}'}\n"
                   f"Observed issue: {story}\n"
                   "Please confirm the correct service category and provide a reference number if a request is created.")
    return {
        "schema_version": "1.0", "report_id": state.get("report_id"), "category": category,
        "priority": priority, "summary": story[:350] or "A local environmental concern was reported.",
        "jurisdiction": {"status": status, "city": "Edmonton" if inside else None, "warnings": []},
        "clarification": None if category != "other" else "What kind of item or issue is it?",
        "reporting": {"reportable": not emergency if inside else None, "requires_311": requires311,
                      "requires_311_reason": assistance, "contact_name": "Edmonton 311" if inside else None,
                      "phone": phone, "url": url, "report_text": report_text,
                      "status": "not_submitted", "submitted": False, "direct_submission_enabled": False},
        "assessment": {"risk": {"level": level, "label": "Estimated", "basis": risk_reason},
                       "requires_311": requires311, "requires_311_reason": assistance,
                       "official_instructions": steps[:3], "official_instructions_url": CITY_GUIDANCE,
                       "materials": materials},
        "steps": steps, "nearby_places": [],
        "thank_you": "Thank you for helping keep the community clean and safe.",
        "sources": [{"title": "Edmonton 311 service requests", "url": CITY_GUIDANCE},
                    {"title": "Public space waste sorting", "url": CITY_SORTING},
                    {"title": "Managing waste in public spaces", "url": CITY_LITTER}],
        "warnings": ["The advanced AI analysis was unavailable, so this is basic safety-first guidance; live locations and 311 service routing have not been verified."],
        "meta": {"llm_used": False, "processing_warning": "The advanced AI model could not be reached or the planning workflow failed."},
    }
