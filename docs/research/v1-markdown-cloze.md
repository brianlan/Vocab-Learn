# Safe Markdown and cloze rendering research

Reviewed: 2026-10-31. Installed parser: `markdown-it-py==4.0.0` in the requested Python 3.11 environment. This is a disposable parser experiment, not an application implementation or a decision about preserving learning progress.

## Recommended authoring contract

- Question and explanation support ordinary Markdown, including `**bold**`. Underline uses exact lowercase, attribute-free `<u>underlined text</u>`, paired within one inline block and properly nested with Markdown formatting. `__text__` means bold under CommonMark, not underline.
- Questions recognize `{{blank}}` in parsed prose and number actual blanks in reading order. Formatting may wrap several blanks: `**{{blank}}** and <u>{{blank}}</u>` produces blanks 1 and 2.
- Write a literal marker as `\{{blank}}`, in an inline/fenced code span, in a Markdown link destination, or in an angle-bracket URL autolink. A bare unlinked URL is prose under this parser preset; escape its marker or use an autolink. Markers in rejected Markdown link syntax can likewise become prose. This must be documented rather than silently treating every substring that resembles a URL as a protected destination.
- Markers inside an HTML token, including attributes, comments, and HTML blocks, stay literal. Text between separately escaped inline HTML tags remains ordinary prose; e.g. a marker between escaped `<span>` tags can still be a real blank, but no authored span becomes a DOM element.
- Explanation uses the same formatting pipeline with cloze recognition disabled. Its literal marker text does not create blanks. The reference answer remains plaintext, escaped when displayed; neither Markdown rendering nor per-blank answers are introduced.
- Images display alt text only; they never load remote content. Links permit HTTP, HTTPS, mailto, and relative/fragment references, retaining the parser's dangerous-link checks. Protocol-relative and custom-scheme links stay inactive.

These are proposed syntax boundaries. The user has not yet decided whether formatting-only question edits should preserve progress.

## Why the installed parser is sufficient

The project explicitly warns that its CommonMark default allows arbitrary HTML and is unsafe for untrusted input without precautions. Its documented alternatives are sanitizing enabled HTML or disabling arbitrary HTML and selectively supplying safe markup features. Built-in link checks reject dangerous schemes but are not an arbitrary-HTML sanitizer. [Official security guidance](https://github.com/executablebooks/markdown-it-py/blob/v4.0.0/docs/security.md)

The experiment uses the existing Markdown parser to tokenize HTML so a marker inside an attribute cannot be mistaken for prose. Both raw-HTML render rules are replaced with escaped-text rendering. Only validated `<u>` pairs become controlled underline tokens; all other authored HTML remains escaped. This is not a homemade HTML sanitizer: arbitrary HTML is never emitted. A maintained sanitizer is unnecessary for this narrow path; broadening raw-HTML support would require revisiting that boundary.

The parser documents token processing, rule insertion, and renderer overrides. The check adds one inline cloze rule through that extension API; it does not replace the Markdown grammar with regular expressions. [Official architecture](https://github.com/executablebooks/markdown-it-py/blob/v4.0.0/docs/architecture.md), [usage and renderer hooks](https://github.com/executablebooks/markdown-it-py/blob/v4.0.0/docs/using.md)

An important observed trap: full parsing joins escaped/entity text into ordinary text. Replacing `{{blank}}` in final text tokens would therefore turn escaped literal markers into blanks. Recognizing the marker during inline parsing avoids this: backslash escapes, code, link destinations, entities, and HTML tokens are consumed by their own rules first. [Installed-version escape rule](https://github.com/executablebooks/markdown-it-py/blob/v4.0.0/markdown_it/rules_inline/escape.py), [text joining](https://github.com/executablebooks/markdown-it-py/blob/v4.0.0/markdown_it/rules_core/text_join.py), [CommonMark escapes and code](https://spec.commonmark.org/0.31.2/#backslash-escapes)

Only generated blank tokens emit `class="cloze-blank"`, an integer `data-blank`, and a controlled accessible label. Imported classes, IDs, attributes, scripts, SVG, or event handlers cannot forge those elements. A final renderer must use this complete configured path consistently in previews and learning screens; calling the default HTML-enabled renderer elsewhere would lose the boundary.

Underline validation also accounts for Markdown nesting. Unmatched, crossed, attribute-bearing, and standalone block forms stay escaped, so an opening underline cannot remain active beyond the field. Properly nested underline/strong/emphasis remains supported. No generic attributes, custom classes, arbitrary raw links, or plugin-generated HTML are enabled.

## Visible text and possible semantic identity

Parse once, then derive both rendered HTML and a visible-text projection from the same validated tokens. In the check, controlled blanks render and project as `[1]`, `[2]`, etc.; text and code use their displayed content, and inline formatting syntax disappears. Use that question projection for AI context and reading-length measurement rather than counting Markdown delimiters, tag attributes, or link destinations. The later timing implementation should treat numbered placeholders as blanks, not as extra reading words. Keep the original Markdown for editing.

If the user elects to preserve progress for presentation-only edits, a versioned token fingerprint can omit only strong/emphasis/validated-underline wrappers and merge adjacent text. It retains the exact reference answer, meaningful text, blank count/order, block structure, inline-versus-block code and its content, and normalized link destinations/attributes. It does not simply strip every tag or hash visible text: that would miss code and link-target changes. Explanation is not part of the question/answer identity in this experiment.

This establishes technical feasibility, not an adopted edit policy. If source-based duplicate detection or unconditional resets remain the chosen policy, there is no reason to add the fingerprint to production. If used, assign a policy version and review parser upgrades before silently changing identities. Normalization already agreed for field validation must happen before fingerprinting; the experiment does not invent extra answer equivalence or variant rules.

## Reproducible check and limits

Run:

```sh
/home/rlan/anaconda3/envs/mykik_py311/bin/python docs/research/v1-markdown-cloze-check.py
```

Observed result: **57 assertion cases passed**. They cover multiple formatted blanks; correct numbering; escaped/entity/code/URL/HTML literals; paired, nested, unpaired and crossed underlines; no authored cloze DOM; dangerous/custom/protocol-relative links; text-only images; explanation formatting without cloze expansion; identity sensitivity to answers, prose, blanks, code and link targets; and Unicode, quotes, commas and multiline CSV round trips. The standard CSV module's reader/writer handles those quoting cases; strict headers, all-or-nothing validation, duplicate handling and transactions belong to the agreed importer contract. [Python CSV documentation](https://docs.python.org/3.11/library/csv.html)

The check is intentionally a small disposable rendering/identity proof. No sanitizer or other dependencies were installed. No browser DOM/security audit, application integration, corpus-wide fuzzing, or AI calls were performed. Arbitrary HTML, media loading, block-level underline, and full Markdown equivalence are outside the proven contract.
