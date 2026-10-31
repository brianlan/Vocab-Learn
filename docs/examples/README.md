# Flashcard CSV examples

The [V1 Development Specification](../specs/v1.md) defines the current import, identity, rendering and learning rules. Both schemas are implemented in the application's private-deck CSV importer; these files provide ready-to-import sources.

## Generic Cards

Import [cloze-cards.csv](cloze-cards.csv) into a selected private deck. The UTF-8 file has the required `question`, `answer`, and `explanation` columns. The importer must also accept a UTF-8 BOM and quoted commas, quotes, and multiline fields.

- Use `{{blank}}` for each question gap. A card can have several gaps and one reference answer covering all of them.
- Generic Cards also allow ordinary questions without any gaps; one reference answer covers the whole question.
- Question and explanation support CommonMark formatting such as `**bold**`, emphasis, paragraphs, lists, links, and code. Underline uses exact, paired `<u>text</u>` within one inline block.
- Formatting can wrap a gap, for example `**{{blank}}**` or `<u>{{blank}}</u>`.
- Use `\{{blank}}` or inline/fenced code for a literal marker. Markdown link destinations, autolinks, and HTML tokens do not create gaps; a bare unlinked URL is prose and needs escaping if its marker is literal.
- Explanation never expands gap markers. Answer remains plaintext.
- Arbitrary authored HTML is escaped, unsafe links are inactive, and images display alt text without remote loading.

All three fields must be nonblank. Preserve meaningful Markdown indentation and original source; do not strip content while checking whether it is empty. Validate the complete batch before writing, report CSV record numbers on failure, and skip duplicates without overwriting existing cards.

## Vocabulary Cards

[vocabulary-cards.csv](vocabulary-cards.csv) contains source entries with four required columns: `word`, `explanation`, `native_language`, and `target_language`. Header order may vary. Supply one plaintext target expression and its authored meaning explanation; explanations support the same Markdown profile. The application derives example pairs and references rather than requiring them in this CSV.

- `target_language` is `English` or `Spanish`.
- `native_language` is `Chinese` or `Spanish`.
- The languages must differ. Initial pairs are English/Chinese, English/Spanish, and Spanish/Chinese; a same-language entry fails validation.
- Language values use the English names shown in the creation form. They describe learning content; the application interface remains English.
- Both review directions share one card's progress. Changing a generated example does not create a second learning card.

These examples illustrate English-to-Chinese, English-to-Spanish, and Spanish-to-Chinese vocabulary sources. Valid sources persist before asynchronous preparation of their example pairs. The [acceptance record](../implementation/v1-acceptance.md) documents the tested import, generation and language paths.
