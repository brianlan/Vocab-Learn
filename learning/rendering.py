"""One parsed representation for safe display, answer units and learning identity."""
import hashlib
import json
import math
from dataclasses import dataclass
from html import escape
from urllib.parse import urlsplit
from markdown_it import MarkdownIt

MARKER = "{{blank}}"
PRESENTATION = {"strong_open", "strong_close", "em_open", "em_close",
                "underline_open", "underline_close"}


def cloze_rule(state, silent):
    if not state.src.startswith(MARKER, state.pos):
        return False
    if not silent:
        state.push("cloze_blank", "span", 0)
    state.pos += len(MARKER)
    return True


def escaped_html(renderer, tokens, index, options, env):
    return escape(tokens[index].content, quote=False)


def render_blank(renderer, tokens, index, options, env):
    number = tokens[index].meta["number"]
    return (f'<span class="cloze-blank" data-blank="{number}" '
            f'aria-label="Blank {number}">[{number}]</span>')


def make_parser(question=True):
    # Tokenize HTML to keep markers inside attributes atomic, but never emit it.
    md = MarkdownIt("commonmark", {"html": True})
    if question:
        md.inline.ruler.before("text", "cloze", cloze_rule)
    md.add_render_rule("html_inline", escaped_html)
    md.add_render_rule("html_block", escaped_html)
    md.add_render_rule("cloze_blank", render_blank)
    md.add_render_rule("image", lambda self, ts, i, opts, env: escape(ts[i].content))
    validate = md.validateLink
    def allowed_link(url):
        try:
            scheme = urlsplit(url).scheme.lower()
        except ValueError:
            return False
        return validate(url) and not url.startswith("//") and scheme in {
            "", "http", "https", "mailto"}
    md.validateLink = allowed_link
    return md


def parse(md, source):
    tokens = md.parse(source)
    number = 0
    for block in tokens:
        stack = []
        for token in block.children or []:
            if token.type == "cloze_blank":
                number += 1
                token.meta["number"] = number
            if token.type == "html_inline" and token.content == "<u>":
                stack.append(["u", token, True])
            elif token.type == "html_inline" and token.content == "</u>":
                if stack and stack[-1][0] == "u":
                    _, opening, valid = stack.pop()
                    if valid:
                        for item, kind, nesting in ((opening, "underline_open", 1),
                                                     (token, "underline_close", -1)):
                            item.type, item.tag = kind, "u"
                            item.nesting, item.content = nesting, ""
                else:
                    for item in stack:
                        if item[0] == "u":
                            item[2] = False
            elif token.nesting == 1:
                stack.append([token.tag, token, True])
            elif token.nesting == -1:
                while stack and stack[-1][0] == "u":
                    stack.pop()
                if stack:
                    stack.pop()
    return tokens, number


def inline_key(children):
    result = []
    for token in children:
        if token.type in PRESENTATION:
            continue
        if token.type == "text" and not token.content:
            continue
        key = ("blank", token.meta["number"]) if token.type == "cloze_blank" else (
            token.type, token.tag, token.nesting, token.content,
            tuple(sorted(token.attrs.items())))
        if token.type == "text" and result and result[-1][0] == "text":
            previous = result.pop()
            key = (*previous[:3], previous[3] + token.content, previous[4])
        result.append(key)
    return result


def fingerprint(tokens, answer):
    semantic = [inline_key(t.children or []) if t.type == "inline" else
                (t.type, t.tag, t.nesting, t.content, t.info,
                 tuple(sorted(t.attrs.items()))) for t in tokens]
    payload = json.dumps(["cloze-v1", semantic, answer], ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def visible_text(tokens):
    pieces = []
    for block in tokens:
        if block.type == "inline":
            for token in block.children or []:
                if token.type == "cloze_blank":
                    pieces.append(f'[{token.meta["number"]}]')
                elif token.type in {"text", "code_inline", "html_inline", "image"}:
                    pieces.append(token.content)
                elif token.type in {"softbreak", "hardbreak"}:
                    pieces.append("\n")
            pieces.append("\n")
        elif block.type in {"fence", "code_block", "html_block"}:
            pieces.append(block.content + "\n")
    return "".join(pieces).rstrip("\n")


def view(source, answer="reference", question=True):
    md = make_parser(question)
    tokens, count = parse(md, source)
    return (md.renderer.render(tokens, md.options, {}), count,
            visible_text(tokens), fingerprint(tokens, answer))


@dataclass(frozen=True)
class Rendered:
    html: str
    text: str
    blanks: int
    reading_count: int
    identity: str


def render(source, answer="", question=False):
    md = make_parser(question)
    tokens, count = parse(md, source)
    text = visible_text(tokens)
    reading = []
    for block in tokens:
        if block.type == "inline":
            reading.extend(t.content for t in block.children or [] if t.type in {"text", "code_inline", "html_inline", "image"})
        elif block.type in {"fence", "code_block", "html_block"}:
            reading.append(block.content)
    return Rendered(md.renderer.render(tokens, md.options, {}), text, count,
                    sum(not c.isspace() for c in "".join(reading)), fingerprint(tokens, answer))


def recall_budget(units, question_count, reference):
    return max(12, math.ceil(5 * units + question_count / 20 + sum(not c.isspace() for c in reference) / 5))


def highlight(sentence, expression, start):
    if start < 0 or sentence[start:start + len(expression)] != expression:
        raise ValueError("The highlighted expression does not match its saved position.")
    before, after = sentence[:start], sentence[start + len(expression):]
    return escape(before) + "<strong class=\"target-word\">" + escape(expression) + "</strong>" + escape(after)
