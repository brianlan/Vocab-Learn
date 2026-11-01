# Continuous practice without study runs

Practice is an ongoing activity that learners can leave and resume at any time; explicit runs added lifecycle choices without a corresponding lesson goal or session report. Remove StudyRun and its run-local Deferral model, retain immutable Presentation/Attempt/history records, and expose selection through `next_question(user, deck=None)`; only the current question stays fixed, while eligible unseen Ready cards are selected randomly.

Skip and a confirmed unassessed exit temporarily defer the current card for 30 minutes without changing its FSRS due, memory, collection, streak or direction. This is separate from the learning schedule and shared across visits; an already accepted assessment may still finish. Stale presentations cannot defer a newer source or progress version.

The migration copies the selected deck scope to each Presentation and translates recent valid neutral actions into remaining deferral time before removing run associations and tables. It preserves card memory, presentations, recordings/transcripts, scored reviews and original processing deadlines. Run metadata is intentionally removed; rolling back requires the pre-migration cold backup and matching image.
