# Verify Safe Markdown Rendering and Cloze Compatibility

Id: 13
Parent: [Vocab-Learn Browser V1 Decision Map](../map.md)
Type: research
Labels: wayfinder:research
Mode: AFK
Status: resolved
Assignee: /root/research_audio
Blocked by: 04, 06
Research branch: research/markdown-cloze
Research commit: 877584e8b75f9960c8accfdf6e52fc6bd4ee7518
Prototype branch: prototype/spoken-card-ui
Prototype commit: d15c55773e6d52feb0fecc7b280213fc222fee90

## Question

What is the smallest reliable Python rendering path for Markdown in question/explanation text, including bold and an explicitly documented underline syntax, while preserving numbered cloze blanks and treating imported content as untrusted?

The environment already has markdown-it-py 4.0.0. Investigate that existing parser first. Underline is not standard CommonMark; prefer a clear supported convention such as a narrowly allowed `<u>text</u>` form if it can be rendered safely. Do not hand-roll a Markdown parser or HTML sanitizer. If a maintained sanitizer is needed, identify a minimal option and ask the parent before changing the shared environment.

Check ordinary formatting, multiple blanks inside formatted text, literal blank markers in code/URLs, raw HTML and dangerous links, escaped markers, and CSV quoting/multiline Unicode. Establish a consistent visible-text/blank representation for grading and timing, and assess whether inline formatting-only edits can preserve learning identity without ignoring meaningful text, answer, blank, code, or link-target changes.

Produce an English primary-source research note and a small assert-based check on an isolated research branch. No production application, paid calls, credential reads, or main tracker changes by the research worker.

## Answer

Resolved on 2026-10-31. The existing `markdown-it-py==4.0.0` supports the required path without a new dependency: tokenize Markdown, recognize actual cloze markers through an inline extension, escape all authored HTML, and promote only validated, paired, attribute-free `<u>` wrappers. The study rendering and visible-text/identity projections share the parsed tokens.

The [research note](../../../research/v1-markdown-cloze.md) and [reproducible check](../../../research/v1-markdown-cloze-check.py) record 57 passing assertion cases and primary sources. They establish safe formatting, escape/code/URL provenance, numbering, and a possible presentation-insensitive identity; adopting an editing policy is separate from these facts. Research source: `research/markdown-cloze` at `877584e8b75f9960c8accfdf6e52fc6bd4ee7518`.

The parent additionally generated a [CSV example](../../../examples/cloze-cards.csv) and rendered preview (local-only reference: `/tmp/vocab-learn-prototype-card-ui/docs/prototypes/card-review-prototype/markdown-preview.html`), then used CDP to check actual bold/underline, blank numbering, explanation isolation, and seven DOM payload probes. No executable tags/events, counterfeit cloze elements, leaked underline, remote image loads, or runtime errors were observed in those probes. Preview snapshot: `prototype/spoken-card-ui` at `d15c55773e6d52feb0fecc7b280213fc222fee90`.

These bounded checks are not a complete security audit or production importer validation. No real user data, model calls, credentials, sanitizer package, or production application was involved.
