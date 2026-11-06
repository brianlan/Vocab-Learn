"""Lexical preparation in the existing explanation format; no database writes."""
import re


def parts(explanation):
    definition = explanation
    pronunciations = []
    reading = re.compile(r"/([^/\n]+)/\s*(\([^()\n]*\))?")
    cursor = 0
    text = explanation.lstrip()
    while match := reading.match(text, cursor):
        pronunciations.append({"ipa": "/" + match[1] + "/", "label": (match[2] or "").strip("()"), "variety": ""})
        cursor = match.end()
        next_start = re.match(r"[\s,;]*", text[cursor:]).end() + cursor
        if not reading.match(text, next_start):
            break
        cursor = next_start
    separator = re.match(r"\s*:\s*", text[cursor:]) if pronunciations else None
    if separator:
        definition = text[cursor + separator.end():]
    else:
        pronunciations = []
    synonyms = None
    suffix = re.search(r"\s*\[synonyms\s*:\s*([^\[\]]*)\]\s*$", definition, re.I)
    if not suffix:
        suffix = re.search(r"\n\s*\n(?:\*\*)?Synonyms:(?:\*\*)?\s*(.*?)\s*$", definition, re.I | re.S)
    if suffix:
        raw = suffix[1].strip()
        if raw.lower().rstrip(".") in {"", "none", "no close synonyms"}:
            synonyms = []
        else:
            synonyms = [item.strip() for item in re.split(r"[,;](?![^()]*\))", raw) if item.strip()]
        definition = definition[:suffix.start()]
    return {"explanation": definition.strip(), "pronunciations": pronunciations, "synonyms": synonyms}


def missing(explanation):
    return [name for name, value in parts(explanation).items() if value is None or value == "" or (name == "pronunciations" and not value)]


def combine(original, additions):
    """Append missing teaching details without rewriting a supplied definition."""
    supplied = parts(original)
    text = original if supplied["explanation"] else additions["explanation"]
    if "pronunciations" in additions:
        readings = []
        for pronunciation in additions["pronunciations"]:
            label = "; ".join(filter(None, [pronunciation["variety"], pronunciation["label"]]))
            readings.append(pronunciation["ipa"] + (" (" + label + ")" if label else ""))
        text = ", ".join(readings) + ": " + text
    elif not supplied["explanation"] and supplied["pronunciations"]:
        text = ", ".join(p["ipa"] + (" (" + p["label"] + ")" if p["label"] else "") for p in supplied["pronunciations"]) + ": " + text
    if "synonyms" in additions:
        text += "\n\nSynonyms: " + ("; ".join(additions["synonyms"]) if additions["synonyms"] else "No close synonyms")
    elif not supplied["explanation"] and supplied["synonyms"] is not None:
        text += "\n\nSynonyms: " + ("; ".join(supplied["synonyms"]) if supplied["synonyms"] else "No close synonyms")
    return text
