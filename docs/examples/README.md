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

[vocabulary-cards.csv](vocabulary-cards.csv) contains the original four-column sources. In the development creation increment,
the required columns are `word`, `native_language`, and `target_language`; `explanation` is optional and header order may vary.
[vocabulary-auto.csv](vocabulary-auto.csv) demonstrates word-only content with explicit languages. Omit the explanation column
or leave individual cells blank for automatic learner-definition, pronunciation and synonym preparation. Supply an explanation
to specify an intended meaning; it supports the same Markdown profile and is preserved. The application prepares example pairs
after the teaching details are complete. Production gains these capabilities only after a separately requested release.
The [structured-field increment](../specs/vocabulary-fields.md) stores the definition, pronunciation and synonyms separately;
these CSV columns and old combined explanation sources remain supported.

- `target_language` is `English` or `Spanish`.
- `native_language` is `Chinese` or `Spanish`.
- The languages must differ. Initial pairs are English/Chinese, English/Spanish, and Spanish/Chinese; a same-language entry fails validation.
- Language values use the English names shown in the creation form. They describe learning content; the application interface remains English.
- Both review directions share one card's progress. Changing a generated example does not create a second learning card.
- Without an explanation, a same-expression/language card in the selected deck is skipped, including archived and not-ready
  cards. Other decks are independent. With an explanation, different teaching senses remain separate cards.

These examples illustrate English-to-Chinese, English-to-Spanish, and Spanish-to-Chinese vocabulary sources. Valid sources persist before asynchronous completion and example preparation. The [acceptance record](../implementation/v1-acceptance.md) documents the original import, generation and language paths; the [creation increment](../specs/vocabulary-creation.md) owns the new behavior.
