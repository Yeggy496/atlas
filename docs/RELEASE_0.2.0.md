# v0.2.0 — practical planning workflow

Existing browser workspaces and the shared CP-SAT model remain compatible. No new runtime dependencies were introduced.

- Start with personal tasks; examples are opt-in and use the current week.
- Unrecognized input is visibly pending. Solving cannot silently ignore it.
- Same-plan multi-tab conflicts have explicit recovery choices, including when another tab deletes its copy.
- Validation runs guard against late responses. Saving blocks conflicting navigation and closing the editor.
- Forms offer all half-hour durations and precise weekday/time deadlines; constraint descriptions come from the actual model fields.
- Dialogs keep focus, restore the opener, and protect unsaved drafts. Resource renaming stays visible during search; production candidate machines remain editable.
- Repeat activities on chosen dates, search/filter lists, edit/fix/unlock calendar events, rename plans, delete local history entries, and undo up to ten content edits per session.
- Week/day/agenda views show early and late tasks clearly. Mobile adds history navigation, larger action targets, and navigation between input and results.
- Imports support Chinese columns, actual Excel time cells, current resource names/IDs, and warnings for possible duplicates. Text is retained and parsed in user-triggered chunks.
- Both plan JSON and workspace backups can restore editable models. Imported results never establish user review or solver correctness. An infeasible result no longer erases the previous feasible baseline.
- Solver facts appear without a paid model request. Optional AI narration uses those facts and is cached per run/activity.

Verification uses real API/CP-SAT calls and isolated browser storage. Reliability race tests deliberately delay validation responses; long-text chunk tests substitute a parser response to verify client state handling, and do not measure model accuracy. The live deployment is separately checked with its configured DeepSeek provider.

Boundaries remain: 30-minute precision, at most 100 activities/50 resources/200 explicit constraints, one-day activity intervals, local browser persistence, bounded solver time, and single-constraint repair candidates. FEASIBLE means a validated feasible schedule, not a proof of global optimality. Stability is a weighted objective. No whole-school scalability, cross-device synchronization, model training, or original CP-SAT algorithm is claimed.
