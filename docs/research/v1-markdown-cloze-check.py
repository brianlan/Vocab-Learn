"""Disposable markdown-it-py 4.0.0 rendering/identity experiment, not app code."""

import csv
import hashlib
import io
import json
from html import escape
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

ASSERTIONS = 0


def expect(condition, message=""):
    global ASSERTIONS
    ASSERTIONS += 1
    assert condition, message


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


def check():
    html, count, visible, base = view('A {{blank}} and {{blank}}.')
    expect(count == 2 and visible == 'A [1] and [2].')
    expect(html.count('class="cloze-blank"') == 2)
    formatted = view('A **{{blank}}** and <u>{{blank}}</u>.')
    expect(formatted[1:] == (count, visible, base))
    expect('<strong>' in formatted[0] and '<u>' in formatted[0])
    expect(view('A <u>**{{blank}}**</u> and *{{blank}}*.')[3] == base)
    expect(view('A {{blank}} and {{blank}}.', 'changed')[3] != base)
    expect(view('A {{blank}} or {{blank}}.')[3] != base)
    expect(view('A {{blank}}.')[3] != base)
    expect(view('**same** {{blank}}')[3] == view('<u>same</u> {{blank}}')[3])
    expect(view('`same` {{blank}}')[3] != view('same {{blank}}')[3])
    expect(view('`one` {{blank}}')[3] != view('`two` {{blank}}')[3])
    expect(view('[same](https://one.test) {{blank}}')[3] != view('[same](https://two.test) {{blank}}')[3])
    for literal in ('\\{{blank}}', '`{{blank}}`', '```\n{{blank}}\n```', '[x](https://example.test/{{blank}})', '&#123;&#123;blank}}', '<span title="{{blank}}">x</span>', '<script>{{blank}}</script>'):
        expect(view(literal)[1] == 0, literal)
    expect(view('\\\\{{blank}}')[1] == 1)
    expect(view('<u>{{blank}}</u>')[1] == 1)
    expect('&lt;u&gt;' in view('<u>unclosed {{blank}}')[0])
    expect('&lt;u&gt;' in view('<u>\n\ntext\n\n</u>')[0])
    for malformed in ('<u>**cross</u>** {{blank}}', '**<u>cross**</u> {{blank}}', '<u><u>**cross</u>**</u> {{blank}}', '</u>x {{blank}}'):
        expect('<u>' not in view(malformed)[0], malformed)
    nested = view('<u>outer <u>inner</u></u> {{blank}}')
    expect(nested[0].count('<u>') == nested[0].count('</u>') == 2)
    explanation = view('**note** <u>under</u> {{blank}}', question=False)
    expect(explanation[1] == 0 and '{{blank}}' in explanation[0])
    expect('<strong>note</strong>' in explanation[0] and '<u>under</u>' in explanation[0])
    expect(view('<https://example.test/{{blank}}>')[1] == 0)
    expect(view('[{{blank}}](https://example.test)')[1] == 1)
    expect(view('<span title="{{blank}}">x</span> {{blank}}')[1] == 1)
    for raw in ('<span class="cloze-blank" data-blank="9">x</span>', '<u onclick="alert(1)">x</u>', '<img src=x onerror=alert(1)>', '<svg onload=alert(1)>x</svg>', '<!-- {{blank}} -->'):
        output = view(raw)[0]
        expect('<span' not in output and '<img' not in output and ('<svg' not in output))
        expect('<u ' not in output and '<!--' not in output)
    for url in ('javascript:alert(1)', 'JaVaScRiPt:alert(1)', 'java&#x73;cript:alert(1)', 'data:text/html,x', 'file:///etc/passwd', 'vbscript:x', 'custom:action', '//example.test/path'):
        expect('<a ' not in view(f'[click]({url})')[0], url)
    expect('https://%5Bbad' in view('[click](https://[bad)')[0])
    expect('<a href="https://example.test' in view('[safe](https://example.test)')[0])
    expect('<img' not in view('![alt](https://example.test/pixel)')[0])
    expect(view('![{{blank}}](https://example.test/pixel)')[1] == 0)
    row = {'question': '**Unicode 日本語**, {{blank}}\n<u>second</u>', 'answer': 'one, "two"', 'explanation': '**bold**\n<u>underlined</u>'}
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=list(row))
    writer.writeheader()
    writer.writerow(row)
    expect(list(csv.DictReader(io.StringIO(buffer.getvalue(), newline=''))) == [row])
    expect(view(row['question'], row['answer'])[1] == 1)
    print(f'PASS: {ASSERTIONS} assertion cases for formatting, cloze, identity, HTML/links, CSV')


if __name__ == "__main__":
    check()
