"""Structured teaching details and the legacy source-text adapter; no database writes."""
import re
from .rendering import make_parser


def _read_label(text, start):
    depth, cursor, result = 1, start + 1, []
    escapes = {"\\": "\\", "(": "(", ")": ")", "n": "\n", "r": "\r"}
    while cursor < len(text):
        character = text[cursor]
        if character == "\\" and cursor + 1 < len(text) and text[cursor + 1] in escapes:
            result.append(escapes[text[cursor + 1]])
            cursor += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return "".join(result), cursor + 1
        result.append(character)
        cursor += 1
    return None


def _pronunciation_text(pronunciations):
    readings = []
    for pronunciation in pronunciations:
        label = "; ".join(filter(None, [pronunciation["variety"], pronunciation["label"]]))
        label = label.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\n", "\\n").replace("\r", "\\r")
        readings.append(pronunciation["ipa"] + (" (" + label + ")" if label else ""))
    return ", ".join(readings)


def _footer(definition):
    tokens = make_parser(question=False).parse(definition)
    block = next((token for token in reversed(tokens) if token.level == 0 and token.map), None)
    if block is None or block.type != "paragraph_open":
        return None
    lines = [0] + [match.end() for match in re.finditer(r"\r\n?|\n", definition)]
    start = lines[block.map[0]]
    end = lines[block.map[1]] if block.map[1] < len(lines) else len(definition)
    paragraph = definition[start:end]
    suffix = re.search(r"\s*\[synonyms\s*:\s*([^\[\]]*)\]\s*$", paragraph, re.I)
    if not suffix:
        suffix = re.search(r"^[ \t]*(?:\*\*)?Synonyms:(?:\*\*)?\s*(.*?)\s*$", paragraph, re.I | re.S)
    if suffix is None:
        return None
    cut = start + suffix.start()
    separator = re.search(r"(?:\r\n?|\n)(?:[ \t]*(?:\r\n?|\n))*[ \t]*$", definition[:cut])
    return (separator.start() if separator else cut), suffix[1].strip()


def _parts(explanation):
    definition = explanation
    pronunciations = []
    reading = re.compile(r"/([^/\n]+)/")
    cursor = 0
    text = explanation.lstrip()
    while match := reading.match(text, cursor):
        cursor = match.end() + re.match(r"\s*", text[match.end():]).end()
        label = ""
        if text[cursor:cursor + 1] == "(":
            parsed = _read_label(text, cursor)
            if parsed is None:
                pronunciations = []
                break
            label, cursor = parsed
        variety, delimiter, remainder = label.partition("; ")
        if variety not in {"US", "UK", "Spain"}:
            variety, remainder = "", label
        pronunciations.append({"ipa": "/" + match[1] + "/", "label": remainder, "variety": variety})
        next_start = re.match(r"[\s,;]*", text[cursor:]).end() + cursor
        if not reading.match(text, next_start):
            break
        cursor = next_start
    separator = re.match(r"[ \t]*:[ \t]*(?:\r?\n[ \t]*\r?\n)?", text[cursor:]) if pronunciations else None
    if separator:
        definition = text[cursor + separator.end():]
        pronunciation_source = text[:cursor].strip()
    else:
        pronunciations = []
        pronunciation_source = ""
    synonyms = None
    synonym_source = ""
    footer = _footer(definition)
    if footer:
        cut, raw = footer
        synonym_source = definition[cut:].strip()
        if raw.lower().rstrip(".") in {"", "none", "no close synonyms"}:
            synonyms = []
        else:
            synonyms = [item.strip() for item in re.split(r"[,;](?![^()]*\))", raw) if item.strip()]
        definition = definition[:cut]
    return ({"explanation": definition, "pronunciations": pronunciations, "synonyms": synonyms},
            {"explanation": definition, "pronunciations": pronunciation_source, "synonyms": synonym_source})


def parts(explanation):
    return _parts(explanation)[0]


def edited_details(card, explanation):
    values, changed = _parts(explanation)
    if card.definition is not None:
        _, original = _parts(card.explanation)
        saved = details(card)
        for name in values:
            if original[name].replace("\r\n", "\n") == changed[name].replace("\r\n", "\n"):
                values[name] = saved[name]
    return values


def details(card):
    if card.definition is None:
        return parts(card.explanation)
    return {"explanation": card.definition, "pronunciations": card.pronunciations, "synonyms": card.synonyms}


def source(card):
    return {**{key: getattr(card, key) for key in ["word", "target_language", "native_language"]}, **details(card)}


def columns(values):
    return {"definition": values["explanation"], "pronunciations": values["pronunciations"], "synonyms": values["synonyms"]}


def missing(values):
    return [name for name, value in values.items() if value is None or (isinstance(value, str) and not value.strip()) or
            (name == "pronunciations" and not value)]


def combine(original, additions):
    """Append missing teaching details without rewriting a supplied definition."""
    supplied = parts(original)
    text = original if supplied["explanation"].strip() else additions["explanation"]
    if "pronunciations" in additions:
        text = _pronunciation_text(additions["pronunciations"]) + ":\n\n" + text
    elif not supplied["explanation"].strip() and supplied["pronunciations"]:
        text = _pronunciation_text(supplied["pronunciations"]) + ":\n\n" + text
    if "synonyms" in additions:
        text += "\n\nSynonyms: " + ("; ".join(additions["synonyms"]) if additions["synonyms"] else "No close synonyms")
    elif not supplied["explanation"].strip() and supplied["synonyms"] is not None:
        text += "\n\nSynonyms: " + ("; ".join(supplied["synonyms"]) if supplied["synonyms"] else "No close synonyms")
    return text
