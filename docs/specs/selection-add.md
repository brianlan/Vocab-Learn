# Selection add and personal Settings

This development increment implements [issue #10](https://github.com/brianlan/Vocab-Learn/issues/10).
It reuses [Vocabulary creation and completion](vocabulary-creation.md); no provider prompt, practice rule or
global duplicate policy changes. Production deployment requires a separate explicit request.

## Using selection add

Select a word or phrase in a card's learning content. A small **Add to [Deck]** action appears beside the selection;
selection alone creates nothing. The adjacent picker shows the captured expression and lets you choose an active
private Deck and a temporary language pair. With a valid remembered destination, the main action saves directly.
First use or an unavailable remembered Deck requires **Choose a deck**, not a silent first-Deck default. Without
an active Deck, the picker links to the existing **Create a deck** page.

Eligible content includes Generic questions/reference answers/explanations, Vocabulary expressions/definitions/synonyms,
each example sentence, unanswered practice cues, revealed answers and available transcripts. Inline formatting may span
one selection inside one content region. Editing fields, navigation, controls, hidden content and selections crossing
regions are excluded. Pronunciation and interface labels are not language-tagged learning regions.

Outer whitespace is trimmed and selected whitespace/line-break runs become spaces. Case, punctuation, accents,
apostrophes and hyphens stay intact; there is no stemming, lemmatization, translation or lexical correction.
Only the expression is saved, with a blank explanation. Surrounding context, source URL and hidden reference fields
are neither captured nor submitted. Ordinary completion chooses a broadly useful learner sense, which may differ
from the reading context; use normal source authoring when a particular sense is required.

**Added to [Deck] · Preparing** means the source and preparation intent are saved, not that a model has finished.
The page does not navigate or wait for completion. **Already in [Deck]** reuses the exact expression/language duplicate
in that Deck, including archived cards. Archived duplicates are identified and remain archived; no content, progress,
schedule or preparation job is overwritten or duplicated. A card link provides the existing detail/status page.

The control does not take focus when a selection changes or intercept copying. Its buttons and picker work with the
keyboard; Escape and outside interaction dismiss it. Picker interaction retains captured text when native selection
collapses. Positioning accounts for scrolling and viewport edges. Request data is captured before submission; repeated
pending clicks are disabled, failed additions require explicit same-data Retry, and late feedback cannot claim a newer
selection was added. No automatic retry or paid call is introduced.

## Preferences and language precedence

**Settings** is in the account area. **Enable selection add** defaults to on and **Default language pair** defaults to
English → Chinese. Saving applies to this account across devices on subsequent page loads. Existing accounts need no
preference row for these defaults; page reads create none. The endpoint checks the saved enable flag on every request,
so an old open toolbar cannot bypass a later disable. Normal creation and API-key authoring remain available.

The last accepted create/duplicate destination is browser-local and scoped by signed-in account. Tentative choices and
failed requests are not remembered. Unavailable browser storage falls back to page-local memory. A remembered ID is
resolved only against the current account's active Deck choices; an archived/missing destination needs a fresh choice.
Another account's destination is never adopted. Reload after creating/archiving a Deck elsewhere to refresh choices.

Supported pairs are English → Chinese, English → Spanish and Spanish → Chinese. For each new selection:

1. An explicit temporary picker choice wins for that operation, without changing Settings.
2. Otherwise reliable metadata describes the **visible selected text**, combined with the configured native language.
   An invalid combination, such as Spanish content with native Spanish, requires an explicit supported pair.
3. Unknown-language regions, including Generic authored content, use the configured default pair.

Known unsupported target-language regions offer no add action. A Chinese Production cue is Chinese, not its hidden
English/Spanish expected answer. Practice metadata comes only from the frozen visible cue; legacy unknown metadata
stays unknown rather than consulting mutable parent fields or exposing hidden content.

## Session route and persistence

`POST /selection-add/` requires a signed-in active account, the normal session CSRF token and JSON containing exactly
`deck_id`, `text`, `target_language` and `native_language`. The Deck must be owned and active. Requests are limited to
8 KiB and expressions to 500 characters. Malformed, extra or unsupported fields are rejected without creating work.
The endpoint calls `authoring.create_card` with `explanation=""`; it returns only `created`, `card_url` and `archived`
(201 for creation, 200 for a duplicate). A disabled account receives a safe rejection even from a stale page.
No authoring credential or generated definition is embedded in bootstrap data or returned by this route.

Migration 0011 adds only one-to-one learner preferences. It does not backfill defaults or rewrite users, cards,
examples, schedules, presentations, attempts, jobs, credentials or history. Existing API-key-only routes keep their
authentication/response contracts; browser selection does not call them.

The floating UI lives outside practice's action container, with a separate script and event handlers. Opening it,
choosing a Deck or saving adds no clock pause, recording action, answer reveal, scored review or frozen-snapshot update.
Dynamic answer HTML receives the same visible-region semantics without reinitializing the controller.

## Development verification

Use an isolated database, not production data. In the repository's Python environment:

```sh
validation_dir="$(mktemp -d /tmp/opencode/selection-add-XXXXXX)"
export APP_DATA_DIR="$validation_dir" DATABASE_PATH="$validation_dir/db.sqlite3"
python manage.py test learning.tests --noinput
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
git diff --check
```

Browser tests run explicitly, outside normal Django discovery. They require the development-only Playwright Python
installation and a desktop Chromium executable; neither is a new application dependency. Repeat both commands with
Chrome and Edge paths:

```sh
export PLAYWRIGHT_CHROMIUM_EXECUTABLE=/path/to/chrome-or-edge
python -m unittest learning.tests.browser_selection_add -v
python manage.py test learning.tests.browser_selection_integration --noinput
```

The first module exercises real browser selections, copy/keyboard/focus, popup bounds, storage, language precedence
and asynchronous request states against isolated intercepted responses. The second serves the real Django application,
uses session cookies and CSRF, and verifies Settings/stale-disable, creation/duplicates, all frozen cue languages and
dynamic practice answers. Its synthetic microphone checks that selection add neither acquires nor stops recording,
pauses the existing clock nor changes a submitted recording, assessment input, schedule or frozen snapshot.
These checks do not certify physical audio hardware, screen readers, mobile browsers or Safari.
