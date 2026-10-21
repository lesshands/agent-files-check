# agent-files-check

Your agent instruction files (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, Cursor rules, Copilot instructions, Windsurf and
Cline rules) describe the code. The code moves; the files often do not. This check finds the places
where they no longer match, and proves each one from your own git history.

```
$ python3 agent_files_check.py
agent-files-check 0.1.0: 4 agent file(s) read, 2 finding(s)
CLAUDE.md:41  [moved-or-deleted]  `src/components/canvas/todo-list.tsx` is not in the repository. Last removed or
    renamed in 3f2a9c1 (2026-05-02): move canvas examples. It looks like it moved to `src/components/example-canvas/todo-list.tsx`
AGENTS.md:88  [missing-script]  `pnpm run typecheck`: no package.json in the repository (3 checked) defines this script
```

## What it reports

| Kind | When |
|---|---|
| `moved-or-deleted` | A file or folder the instructions name is gone, and git history shows the commit that removed or renamed it (and where it went, when it can tell). |
| `pr-breaks` | On a pull request: this change deletes or renames something the instructions name. The note lands on the line in the pull request. |

It reports only what it can prove. A path that was never in the repository is not reported, because it is usually a
package name, a file made at run time, a branch, or a pattern; most hits from a plain "does this path exist" scan are
those. Sentences that already say a file was removed, lives in another repository, or is the thing *not* to use are skipped.
Gitignored paths are skipped. Translated copies of agent files are skipped. Skills, slash commands and prompt files are
not read, because they describe the user's project, not the repository that ships them.

An `npm run` / `pnpm run` / `yarn run` / `bun run` script check exists behind `--experimental-scripts`. It is off by
default because in testing most of its hits were scripts run in another folder or repository.

## Run it

One command, in a checkout with full history:

```
curl -fsSLO https://raw.githubusercontent.com/lesshands/agent-files-check/v0/agent_files_check.py
python3 agent_files_check.py            # text
python3 agent_files_check.py --format md   # Markdown
python3 agent_files_check.py --diff origin/main...HEAD   # also: what this branch breaks
```

Python 3.8 or newer, standard library only. It never calls a network service and never changes a file.

## In CI (GitHub Actions)

Copy [`examples/agent-files-check.yml`](examples/agent-files-check.yml) to `.github/workflows/`:

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
- uses: lesshands/agent-files-check@v0
```

Findings show as notes on the pull request and in the job summary. Inputs: `fail-on-findings` (default `false`),
`pull-request-only` (report only what this change breaks; default `false`), `path`.

## How well it works

Measured before release on public repositories; see [SCORE.md](SCORE.md) for the method, the labelled findings and the
intervals. Short version: SCORE_SHORT

## What it cannot see

A sentence that names real things and is still wrong: a real function described in the wrong role, an option the code
dropped, a rule the code stopped following. In our own audit of Sentry's agent files, those were most of what mattered;
the write-up, with what we got right and wrong, is at https://audit.lesshands.com.au/sample-sentry.html.

If you would like a person-reviewed read of those, and the files kept true as the code changes, that is what
[Less Hands](https://audit.lesshands.com.au/offer.html) does. The first check on a public repository is free.

## Licence

MIT. Written by Astrid, for Less Hands.
