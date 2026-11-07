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
    definition_start = len(explanation) - len(definition)
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
            {"explanation": definition, "pronunciations": pronunciation_source, "synonyms": synonym_source,
             "definition_start": definition_start})


def parts(explanation):
    return _parts(explanation)[0]


def _blank_parts(explanation):
    """Interpret metadata-only text when a stored blank definition supplies its intent."""
    values, fragments = _parts(explanation)
    if values["explanation"].strip():
        if values["synonyms"] is not None:
            return None
        footer, footer_fragments = _parts("Entry.\n\n" + values["explanation"])
        if footer["explanation"] != "Entry.":
            return None
        values["synonyms"], fragments["synonyms"] = footer["synonyms"], footer_fragments["synonyms"]
    values["explanation"] = fragments["explanation"] = ""
    return values, fragments


def edited_details(card, explanation):
    if not explanation.strip():
        return parts("")
    values, changed = _parts(explanation)
    if card.definition is not None:
        _, original = _parts(card.explanation)
        saved = details(card)
        if not card.definition.strip() and (blank_source := _blank_parts(card.explanation)):
            _, original = blank_source
            blank_edit = _blank_parts(explanation) if original["synonyms"] or not values["explanation"].strip() else None
            if blank_edit:
                values, changed = blank_edit
                match = re.search(_literal(card.definition), explanation)
                saved["explanation"] = match[0] if match else ""
            elif original["synonyms"]:
                frames = []
                legacy = re.fullmatch(r"(.*?)" + _literal(card.definition) + r"((?:\r?\n[ \t]*){2}" +
                                      _literal(original["synonyms"]) + r"\s*)", card.explanation, re.S)
                if legacy and parts(legacy[1] + "Entry.")["explanation"] == "Entry.":
                    frames.append(legacy.groups())
                prefix = explanation[:changed["definition_start"]]
                legacy = re.fullmatch(_literal(prefix) + _literal(card.definition) + r"(.*)", card.explanation, re.S)
                if legacy and parts("Entry." + legacy[1])["explanation"] == "Entry.":
                    frames.append((prefix, legacy[1]))
                for prefix, footer in frames:
                    body = _framed(explanation, prefix, footer)
                    if body is not None:
                        return {**saved, "explanation": body}
                if not changed["synonyms"] and not _footer_fits(explanation, _synonym_text([])):
                    raise ValueError("Close the Markdown fence before changing both the definition and metadata in this legacy source.")
        elif not original["synonyms"] and card.synonyms is not None and card.definition:
            legacy = _definition_frame(card.explanation, card.definition)
            if legacy and legacy[1].strip():
                prefix, footer = legacy
                body = _framed(explanation, prefix, footer)
                if body is not None:
                    return {**saved, "explanation": body}
                edit = _definition_frame(explanation, card.definition)
                if edit:
                    before, after = edit
                    return {**parts(before + "Entry." + after), "explanation": card.definition,
                            **({"pronunciations": card.pronunciations} if _same_lines(before, prefix) else {}),
                            **({"synonyms": card.synonyms} if _same_lines(after, footer) else {})}
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


def _definition_frame(source, definition):
    start = _parts(source)[1]["definition_start"]
    match = re.match(_literal(definition), source[start:])
    if match:
        suffix = source[start + match.end():]
        if parts("Entry." + suffix)["explanation"] == "Entry.":
            return source[:start], suffix
    return None


def recovered_checkpoint(checkpoint, source):
    """Restore complete teaching values only within their recorded source boundaries."""
    if not isinstance(checkpoint, dict):
        return None
    original, values = checkpoint.get("source"), checkpoint.get("details")
    if (not isinstance(original, str) or not isinstance(values, dict) or
            set(values) != {"explanation", "pronunciations", "synonyms"} or not isinstance(values["explanation"], str)):
        return None
    try:
        if render(original).identity != render(source).identity:
            return None
        if not values["explanation"].strip() and values["explanation"] in source and _blank_parts(source):
            return values
        frame = _definition_frame(original, values["explanation"])
        if frame:
            definition = _framed(source, *frame)
            if definition is not None:
                return {**values, "explanation": definition}
    except (TypeError, ValueError):
        pass
    return None


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
