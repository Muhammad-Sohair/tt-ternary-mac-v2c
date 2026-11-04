# v2c Step 4 — switching a Tiny Tapeout submission to another repo or commit

Read from Tiny Tapeout's own documentation on 4 Nov 2026 (no other source). Where the docs are silent this
says **[UNKNOWN]**. Nothing here was tried in the app: submitting and paying are the owner's.

## Changing the repository of a submitted project

https://tinytapeout.com/guides/change-project-repo/ :

1. "Navigate to your project on the Tiny Tapeout submission app (app.tinytapeout.com). Click the 'Change'
   button" (next to the repo URL).
2. "Enter it and click the 'Change Repo' button. Your repo must be based on one of our templates."
3. "For the changes to take effect, you **must** submit a new revision. The project in the newly linked
   repository must have a passing GDS action. Click on the 'Submit a new revision' button to automatically
   fetch the latest build."

The FAQ (https://tinytapeout.com/faq/) points to the same guide.

## Which commit a revision uses

- The change-repo guide: "Submit a new revision … to automatically fetch the latest build."
- The workshop and advanced-workshop guides: make and commit changes, "Check the GDS and Docs actions are
  passing", then "Submit a new revision".
- **[UNKNOWN]**: whether "latest build" means the newest commit's run or the newest *successful* GDS run, and
  whether a specific commit can be chosen. Safe practice (as done for A on 29 Oct): make sure the tip of the
  default branch is the intended commit and its gds, test and docs runs are green, then check in the app
  which commit the revision shows before confirming.

## Tile count and top module

- **[UNKNOWN]**: the docs say nothing about switching to a repo with a different tile count; the FAQ only says
  larger designs "may require additional tiles to be purchased" (app and calculator). C is 2x2, the same as
  A, so this question does not arise if C keeps 2x2.
- **[UNKNOWN]**: nothing about the top module name differing between the old and new repo (A
  `tt_um_msohair_tmac2`, C `tt_um_msohair_tmac2c`). Ask TT before relying on it.

## Deadline

"Designs can be changed up until the shuttle deadline … No new revisions will be accepted after the
deadline. **Make sure you account for the time it takes for the GitHub Actions to run.**"
(https://tinytapeout.com/guides/workshop/submit-your-design/). SKY 26d closes 30 Nov 2026 (checked 27 Oct).

## What this means for A → C

If C is signed off by 22 Nov and the owner chooses C instead of A: in the app, on A's project, "Change" the
repo to `https://github.com/Muhammad-Sohair/tt-ternary-mac-v2c`, then "Submit a new revision" with C's tip
green; confirm the revision shows C's commit. The two [UNKNOWN] points (top-module rename, which build is
fetched) are worth one question to TT before 22 Nov.
