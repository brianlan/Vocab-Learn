"""Structured teaching details and the legacy source-text adapter; no database writes."""
import re
from .rendering import make_parser, render


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
    if not suffix and definition[:start].strip():
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
    if not explanation.strip():
        return parts("")
    values, changed = _parts(explanation)
    if card.definition is not None:
        _, original = _parts(card.explanation)
        saved = details(card)
        if not original["synonyms"] and card.synonyms is not None and card.definition:
            footer = _synonym_text(card.synonyms)
            legacy = re.fullmatch(r"(.*?)" + _literal(card.definition) + _literal(footer), card.explanation, re.S)
            if legacy and parts(legacy[1] + "Entry.")["explanation"] == "Entry.":
                prefix = legacy[1]
                body = _framed(explanation, prefix, footer)
                if body is not None:
                    return {**saved, "explanation": body}
                edit = re.fullmatch(r"(.*?)" + _literal(card.definition) + r"(.*)", explanation, re.S)
                if edit:
                    isolated = parts(edit[1] + "Entry." + edit[2])
                    if isolated["explanation"] == "Entry.":
                        return {**isolated, "explanation": card.definition,
                                **({"pronunciations": card.pronunciations} if _same_lines(edit[1], prefix) else {}),
                                **({"synonyms": card.synonyms} if _same_lines(edit[2], footer) else {})}
                if not changed["synonyms"] and not _footer_fits(explanation, _synonym_text([])):
                    raise ValueError("Close the Markdown fence before changing both the definition and metadata in this legacy source.")
                original["synonyms"] = footer.strip()
        for name in values:
            if _same_lines(original[name], changed[name]):
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


def _same_lines(left, right):
    return left.replace("\r\n", "\n") == right.replace("\r\n", "\n")


def _literal(text):
    return re.escape(text.replace("\r\n", "\n")).replace("\\\n", r"\r?\n")


def _framed(source, prefix, suffix):
    match = re.fullmatch(_literal(prefix) + r"(.*?)" + _literal(suffix), source, re.S)
    return match[1] if match else None


def _synonym_text(synonyms):
    return "\n\nSynonyms: " + ("; ".join(synonyms) if synonyms else "No close synonyms")


def _composition(original, additions):
    supplied = parts(original)
    generated_definition = "explanation" in additions
    body = additions["explanation"] if generated_definition else original
    readings = additions.get("pronunciations", supplied["pronunciations"] if generated_definition else None)
    synonyms = additions.get("synonyms", supplied["synonyms"] if generated_definition else None)
    prefix = _pronunciation_text(readings) + ":\n\n" if readings else ""
    return prefix, body, _synonym_text(synonyms) if synonyms is not None else ""


def _footer_fits(body, footer):
    candidate = body + footer
    parsed = _footer(candidate)
    return parsed is not None and candidate[parsed[0]:].strip() == footer.strip()


def combine(original, additions):
    """Keep generated metadata out of the authored Markdown's open blocks."""
    prefix, body, footer = _composition(original, additions)
    source = prefix + body
    return source + footer if footer and _footer_fits(source, footer) else source


def recovered_details(original, additions, source):
    """Replay known completion layouts; an incompatible record falls back to source extraction."""
    if not isinstance(original, str) or not isinstance(additions, dict):
        return None
    try:
        prefix, body, footer = _composition(original, additions)
        prefixes = [prefix, prefix[:-2] + " "] if prefix.endswith(":\n\n") else [prefix]
        for before in prefixes:
            footers = [footer] if not footer or _footer_fits(before + body, footer) else [footer, ""]
            for after in footers:
                current = _framed(source, before, after)
                if current is not None and render(before + body + after).identity == render(source).identity:
                    definition = current if "explanation" in additions else parts(current)["explanation"]
                    return {**parts(original), **additions, "explanation": definition}
    except (KeyError, TypeError, ValueError):
        return None
    return None
