# v0.2.1 — gray-test readiness

Reproduced issues were fixed without replacing the shared solver or adding runtime dependencies.

- New tasks no longer disappear behind an old search/filter. Empty search results explain that the data remains and offer a reset; candidate-room and demand-resource names are searchable.
- Editing the last task in a category removes now-orphaned category rules with an explicit notice and Undo, instead of rejecting the edit with an unknown-target error.
- TXT/PDF extraction previews the text and lets the user cancel, append, or replace. Input changes are reversible. No model call happens until recognition is requested.
- A newline at position 4,000 cannot produce a 4,001-character request. Chunks avoid splitting a UTF-16 surrogate pair. Long input can be downloaded as text; oversized workspace backups are rejected before creating an unrestorable file.
- Optional activities expose the solver's real 1–10 priority. Priority edits participate in unsaved-draft protection.
- New academic/lab/meeting forms show their resource settings and default to available candidate rooms. Existing activity choices remain untouched; online meetings can explicitly remove room choices.
- Export controls cannot interrupt an ongoing solve. JSON, uploads and binary downloads use a bounded timeout with broad AbortController support. Failed recognition/solves can be retried explicitly.
- Failed local writes retain session drafts across scenario changes and warn before closing. Other unsaved scenes remain visible. Successful saving resumes when storage becomes writable. This memory fallback does not survive a page close, so backups remain necessary.
- Saving one scene cannot resurrect another scene deleted by a different tab.
- Repeat dialogs protect selected dates, respect activity/constraint limits and handle long task names.
- Expensive solves/diagnoses and model requests have independent bounded admission. Overload returns a friendly HTTP 429 and retry hint instead of accumulating unlimited concurrent work; slots are released after errors. Deterministic explanations remain available when model capacity is occupied.
- Model response bodies also have a total deadline, so periodic keep-alive bytes cannot indefinitely extend an inactivity timeout and occupy all model slots.

The baseline failures were reproduced in isolated Chromium sessions. Regression tests exercise real import, validation and solver endpoints; busy-network, timeout and storage-quota cases are simulated explicitly. Existing 30-minute, one-day-interval and browser-local persistence boundaries remain unchanged.
