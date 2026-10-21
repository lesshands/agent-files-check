# How well agent-files-check works

Measured 2026-10-21 on version 0.1.0, before release. Every number here can be rerun: the repository lists, findings,
labels and scripts are in [`eval/`](eval/).

## What was measured

**Precision:** of the findings it reports, how many are real stale references (the sentence presents a file or folder
as being in the repository, and it is not). Each finding was labelled by hand against the repository as it is now, by a
reader who did not write the tool.

**Pull-request mode:** for each finding, go back to the commit that deleted or renamed the path and run the check on
that commit alone (`--diff <commit>^...<commit>`). Would it have flagged the sentence on the day it broke?

## Repositories

From the 300 most-starred GitHub repositories pushed in October 2026, those that carry agent instruction files.

- **Tuning set:** 35 repositories, the same ones behind an earlier hand-check of a plain "does this path exist" scan
  (60 labelled hits, 6 real: 10% precision). The tool's filters were built by reading the misses here.
- **Held-out set:** 45 other repositories, chosen at random (seeded) from the rest, never looked at while building.
  The tool's code was frozen before it ran on them.

## Results

| Set | Findings | Real stale | Precision | 95% interval (Wilson) |
|---|---|---|---|---|
| Held-out (45 repos) | 10 | 9 | 90% | 60% to 98% |
| Tuning (35 repos) | 15 | 13 | 87% | 62% to 96% |

Read these with care:

- **The held-out sample is small.** Ten findings in 45 repositories. Six of the nine real ones come from a single Cursor
  rule file (one repository linked six documents deleted eight months earlier). Counted by distinct file, it is 3 of 4.
- **Findings are rare in popular repositories.** 10 in 45. Most popular projects keep their paths current, or name
  things the tool cannot prove from history. Expect few findings, most of them real.
- **Recall is not measured** and is low by design. The tool stays silent on any path that was never in the
  repository's history, on gitignored paths, on sentences that say a thing is gone or lives elsewhere, and on skills,
  slash commands and prompt files. Of the 6 real stale references in the earlier hand-check, it reports none: two were
  never in the repository's history, one is gitignored today, and three sit in sentences whose wording the tool reads as
  "gone, elsewhere, or not to use" (for example "Never barrel-import from `localDb.ts`").
- **The one held-out false positive:** a Cursor rule naming `.claude/settings.json`, which meant the user's own
  settings file, not one in the repository.
- **The "it looks like it moved to" hint** appeared on 10 findings in testing: right on 6, partly right on 2 (git
  recorded a rename, but the file's role moved to another file), wrong on 2. The two wrong ones came from matching a
  common file name; that rule now fires only for a single file with a unique name, and those two now show no hint.
- **The opt-in script check** (`--experimental-scripts`) is not part of these numbers. In the tuning set 2 of its 33
  first-version hits were real. It stays off by default.

## Pull-request mode

| | References |
|---|---|
| Findings whose agent file already named the path when it was deleted | 20 |
| Flagged by `--diff` on the deleting commit alone | 20 |

The other 5 findings were references written after the path was already gone (for example, an agent file copied in
from another project); no pull request deleted them.

## What it cannot see

Sentences that name real things and are still wrong. In our audit of Sentry's agent files, five errors of that kind
were found by Sentry's own refresh and missed by us; the write-up with the score is at
https://audit.lesshands.com.au/sample-sentry.html.
