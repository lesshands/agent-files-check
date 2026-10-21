#!/usr/bin/env python3
"""agent-files-check: find places where a repository's agent instruction files no longer match the code.

Reads CLAUDE.md, AGENTS.md, GEMINI.md, Cursor rules, Copilot instructions, Windsurf and Cline rules.
Reports only what it can prove from the repository itself:

  moved-or-deleted  a file or folder the instructions name is gone, and git history shows when it went
                    (and, when it can tell, where it went)
  missing-script    (opt-in, --experimental-scripts) a `npm run` / `pnpm run` / `yarn run` / `bun run` script no package.json defines
  pr-breaks         (with --diff) this change deletes or renames something the instructions name

It never calls a network service and never changes a file. Python 3.8+, standard library only.
Run it inside a git checkout with full history (in CI: actions/checkout with fetch-depth: 0).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys

VERSION = "0.1.0"

# Agent instruction files, as git pathspec-style globs over tracked files.
AGENT_FILE_GLOBS = [
    "CLAUDE.md", "*/CLAUDE.md", "CLAUDE.local.md",
    "AGENTS.md", "*/AGENTS.md", "AGENT.md", "*/AGENT.md",
    "GEMINI.md", "*/GEMINI.md",
    ".cursorrules", "*/.cursorrules", ".cursor/rules/*",
    ".windsurfrules", ".windsurf/rules/*",
    ".clinerules", ".clinerules/*",
    ".github/copilot-instructions.md", ".github/instructions/*.md",
]
# Skills, slash commands, sub-agent and prompt files mostly describe the user's project, not the repository that
# ships them, so their paths cannot be checked against this repository. They are not read.

# Words that mean the sentence already says the thing is gone or is an example: the text is then accurate.
ACCURATE_ABSENCE = re.compile(
    r"\b(removed|deleted|no longer|deprecated|migrated|renamed|moved (?:to|from)|replaced|legacy|formerly|"
    r"used to|was dropped|e\.g\.|for example|such as|placeholder|gitignored|generated|created (?:at|on|by)|"
    r"will be created|is created|writes?|outputs?|produces?|gone|previously|instead of|rather than|never|"
    r"do not|don't|not a|is not|isn't|no \w+ files|other repo|separate repo|private repo|clone|"
    r"your (?:project|repo|repository|app)|repo|repository|per-repo|prunes?|excludes?|banned|avoid)\b|~/|\bcd\s",
    re.IGNORECASE,
)
NEGATED_BEFORE = re.compile(r"(\bnot|\bno|\bnever|\bavoid|instead of|rather than|\bNOT)\W{0,3}$", re.IGNORECASE)


def negated_here(line, ref):
    """The words right before this reference negate it: "use `a`, not `b`"."""
    i = line.find("`" + ref)
    if i < 0:
        i = line.find(ref)
    return i > 0 and bool(NEGATED_BEFORE.search(line[max(0, i - 20):i]))


def says_absent(line):
    """The prose around the reference (code spans removed) already says it is gone, elsewhere, or an example."""
    return bool(ACCURATE_ABSENCE.search(CODE_SPAN.sub(" ", line)))


CODE_SPAN = re.compile(r"`([^`\n]{2,200})`")
MD_LINK = re.compile(r"\]\(([^)\s]{2,200})\)")
FENCE = re.compile(r"^\s*(```|~~~)")
EXT_ONLY = re.compile(r"^\*?\.[A-Za-z0-9]{1,8}$")
NAME_EXT = re.compile(r"^[A-Za-z0-9_\-.]+\.[A-Za-z][A-Za-z0-9]{0,7}$")
BAD_CHARS = set(" \t*?<>{}[]$|=,;\"'()!^%")
PLACEHOLDER = re.compile(r"(XXX|YYYY|MM-DD|\.\.\.|…|<|>|your[-_]|example|foo|bar\b|my[-_])", re.IGNORECASE)
RUN_CMD = re.compile(r"\b(npm|pnpm|yarn|bun)\s+run\s+([A-Za-z0-9][A-Za-z0-9:_\-]*)(?![\w.<:/\-|])")


def git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


class Repo:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        top = git(self.root, "rev-parse", "--show-toplevel").strip()
        self.root = top
        self.files = [f for f in git(self.root, "ls-files", "-z").split("\0") if f]
        self.file_set = set(self.files)
        self.dir_set = set()
        self.basenames = {}
        self.stems = set()
        for f in self.files:
            parts = f.split("/")
            for i in range(1, len(parts)):
                self.dir_set.add("/".join(parts[:i]))
            self.basenames.setdefault(parts[-1], []).append(f)
            self.stems.add(os.path.splitext(f)[0])
        self.shallow = git(self.root, "rev-parse", "--is-shallow-repository").strip() == "true"
        self._ignored = {}

    def resolves_anywhere(self, ref):
        """True when some tracked file or folder ends with this relative path (a package-relative or aliased name)."""
        tail = "/" + ref.strip("/")
        for p in self.file_set | self.dir_set | self.stems:
            if p.endswith(tail):
                return True
        return False

    def exists(self, path):
        p = path.strip("/")
        return p in self.file_set or p in self.dir_set or p in self.stems

    def ignored(self, path):
        if path not in self._ignored:
            r = subprocess.run(["git", "-C", self.root, "check-ignore", "-q", "--no-index", path],
                               capture_output=True)
            self._ignored[path] = r.returncode == 0
        return self._ignored[path]

    def _deleted_index(self):
        """One pass over history: every path ever deleted -> (sha, date, subject) of its most recent deletion."""
        if getattr(self, "_deleted", None) is None:
            self._deleted = {}
            out = git(self.root, "log", "--no-renames", "--diff-filter=D", "--name-only",
                      "--format=\x01%h\t%ad\t%s", "--date=short", check=False)
            cur = None
            for line in out.splitlines():
                if line.startswith("\x01"):
                    sha, date, subject = (line[1:].split("\t", 2) + ["", ""])[:3]
                    cur = (sha, date, subject[:100])
                elif line and cur and line not in self._deleted:
                    self._deleted[line] = cur  # log is newest first: keep the most recent deletion
            self._deleted_dirs = {}
            self._deleted_names = {}
            for path, c in self._deleted.items():
                parts = path.split("/")
                for i in range(1, len(parts)):
                    self._deleted_dirs.setdefault("/".join(parts[:i]), (path, c))
                self._deleted_names.setdefault(parts[-1], (path, c))
        return self._deleted

    def history(self, ref, basename_only=False):
        """Last commit that deleted ref (file, folder, or bare file name): dict with commit, date, subject, moved_to."""
        self._deleted_index()
        ref = ref.strip("/")
        if basename_only:
            hit = self._deleted_names.get(ref)
        elif ref in self._deleted:
            hit = (ref, self._deleted[ref])
        else:
            hit = self._deleted_dirs.get(ref)
        if not hit:
            return None
        path, (sha, date, subject) = hit
        is_dir = path != ref and not basename_only
        moved_to = None
        whole = git(self.root, "show", "-M", "--name-status", "--format=", sha, check=False)
        for c in whole.splitlines():
            cols = c.split("\t")
            if cols[0].startswith("R") and len(cols) == 3 and cols[1] == path:
                moved_to = cols[2]
                break
        if moved_to is None:
            name = path.rsplit("/", 1)[-1]
            for c in whole.splitlines():
                cols = c.split("\t")
                if cols[0] == "A" and len(cols) == 2 and cols[1].rsplit("/", 1)[-1] == name:
                    moved_to = cols[1]
                    break
        if moved_to and is_dir:
            suffix = path[len(ref):]
            moved_to = moved_to[: -len(suffix)] if suffix and moved_to.endswith(suffix) else None
        return {"commit": sha, "date": date, "subject": subject, "moved_to": moved_to}


def read_text(repo, path):
    with open(os.path.join(repo.root, path), encoding="utf-8", errors="replace") as fh:
        return fh.read()


TRANSLATION_DIR = re.compile(r"(^|/)(i18n|l10n|translations?|locales?)/", re.IGNORECASE)
CODE_EXT = re.compile(r"\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|kt|swift|c|h|cc|cpp|hpp|cs|rb|php|vue|svelte|scala|ex|exs|sh)$")


def agent_files(repo):
    out = []
    for f in repo.files:
        if TRANSLATION_DIR.search(f):
            continue  # translated copies repeat the original's references
        base = f.rsplit("/", 1)[-1]
        for g in AGENT_FILE_GLOBS:
            if fnmatch.fnmatchcase(f, g) or ("/" not in g and fnmatch.fnmatchcase(base, g) and g == base):
                out.append(f)
                break
    return sorted(set(out))


def clean_ref(raw):
    r = raw.strip().rstrip(".,:;")
    r = re.sub(r"::[A-Za-z_][\w.]*$", "", r)          # path::symbol
    r = re.sub(r":\d+(-\d+)?$", "", r)                 # path:line
    r = r.split("#", 1)[0]
    if r.startswith("./"):
        r = r[2:]
    return r


def looks_like_path(r):
    if not r or len(r) < 3 or len(r) > 160:
        return False
    if any(c in BAD_CHARS for c in r) or "://" in r or r.startswith(("-", "~", "/", "@", "../")):
        return False
    if EXT_ONLY.match(r) or PLACEHOLDER.search(r):
        return False
    if "/" in r:
        segs = [s for s in r.split("/") if s]
        if not segs or any(s in (".", "..") for s in segs):
            return False
        # owner/repo, unit/unit, n/a: one short segment each side with no dot is too ambiguous
        if len(segs) == 2 and "." not in r and not r.endswith("/"):
            return False
        return True
    return bool(NAME_EXT.match(r)) and not r[0].isdigit()


def references(text):
    """Yield (line_no, ref, line_text) for path-like references outside fenced code blocks."""
    in_fence = False
    for i, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        seen = set()
        for m in list(CODE_SPAN.finditer(line)) + list(MD_LINK.finditer(line)):
            ref = clean_ref(m.group(1))
            if ref in seen or not looks_like_path(ref):
                continue
            seen.add(ref)
            yield i, ref, line


def resolve_candidates(agent_path, ref):
    """Where the reference could point: next to the agent file first, then the repository root."""
    base = os.path.dirname(agent_path)
    cands = []
    if base:
        cands.append(os.path.normpath(os.path.join(base, ref)).strip("/"))
    cands.append(ref.strip("/"))
    return cands


def check_paths(repo, files):
    findings = []
    for af in files:
        try:
            text = read_text(repo, af)
        except OSError:
            continue
        elsewhere = set()  # first path segments this file has said live somewhere else
        for line_no, ref, line in references(text):
            cands = resolve_candidates(af, ref)
            if any(repo.exists(c) for c in cands):
                continue
            head = ref.strip("/").split("/")[0]
            if says_absent(line) or negated_here(line, ref):
                elsewhere.add(head)
                continue
            if head in elsewhere:
                continue
            if "/" not in ref.strip("/") and ref in repo.basenames:
                continue
            if repo.resolves_anywhere(ref):
                continue
            if any(repo.ignored(c) for c in cands):
                continue  # gitignored now: a local or generated path, even if it was once tracked
            basename_only = "/" not in ref.strip("/")
            if basename_only and not CODE_EXT.search(ref):
                continue  # a bare data or output file name is too often a run-time file
            if says_absent(line):
                continue
            hist = None
            # nested agent file: history must prove the path next to it, unless the reference
            # starts at a folder that exists at the repository root today
            nested = os.path.dirname(af) != ""
            root_ok = not nested or ref.split("/")[0] in repo.dir_set or ref.startswith(".")
            hist = None
            for c in (cands if root_ok else cands[:1]):
                hist = repo.history(c, basename_only=basename_only)
                if hist:
                    break
            if not hist:
                continue  # never tracked here: likely a package, a runtime file, or another repo. Not reported.
            if hist["moved_to"] and repo.exists(hist["moved_to"]) is False:
                hist["moved_to"] = None
            findings.append({
                "kind": "moved-or-deleted", "file": af, "line": line_no, "ref": ref,
                "evidence": hist, "text": line.strip()[:240],
            })
    return findings


def check_scripts(repo, files):
    pkgs = [f for f in repo.files if f.endswith("package.json") and "node_modules/" not in f]
    if not pkgs:
        return []
    scripts = set()
    for p in pkgs:
        try:
            with open(os.path.join(repo.root, p), encoding="utf-8") as fh:
                data = json.load(fh)
            scripts.update((data.get("scripts") or {}).keys())
        except (OSError, ValueError, AttributeError):
            return []  # unreadable manifest: do not guess
    findings = []
    for af in files:
        try:
            text = read_text(repo, af)
        except OSError:
            continue
        in_fence = False
        for i, line in enumerate(text.splitlines(), 1):
            if FENCE.match(line):
                in_fence = not in_fence
                fence_moved = False
                continue
            if in_fence and re.search(r"(^|\s)cd\s", line):
                fence_moved = True  # commands after a cd run in some other folder or repository
            if in_fence and fence_moved:
                continue
            code = [line] if in_fence else [m.group(1) for m in CODE_SPAN.finditer(line)]
            for m in (mm for c in code for mm in RUN_CMD.finditer(c)):
                name = m.group(2).rstrip(".:")
                if name in scripts or PLACEHOLDER.search(name) or says_absent(line):
                    continue
                findings.append({
                    "kind": "missing-script", "file": af, "line": i, "ref": f"{m.group(1)} run {name}",
                    "evidence": {"package_json_files": len(pkgs)}, "text": line.strip()[:240],
                })
    return findings


def check_diff(repo, files, diff_range):
    out = git(repo.root, "diff", "-M", "--name-status", diff_range)
    gone = {}
    for l in out.splitlines():
        cols = l.split("\t")
        if cols and cols[0][:1] in ("D", "R") and len(cols) >= 2:
            gone[cols[1]] = cols[2] if cols[0].startswith("R") and len(cols) == 3 else None
    if not gone:
        return []
    gone_dirs = {}
    for g in gone:
        parts = g.split("/")
        for i in range(1, len(parts)):
            gone_dirs.setdefault("/".join(parts[:i]), g)
    findings = []
    for af in files:
        if af in gone:
            continue
        try:
            text = read_text(repo, af)
        except OSError:
            continue
        for line_no, ref, line in references(text):
            if says_absent(line):
                continue
            cands = resolve_candidates(af, ref)
            bare = "/" not in ref.strip("/")
            if bare and CODE_EXT.search(ref) and ref not in repo.basenames:
                cands = cands + [g for g in gone if g.rsplit("/", 1)[-1] == ref][:1]
            for c in cands:
                c = c.strip("/")
                hit = c if c in gone and not repo.exists(c) else None
                if hit is None and c in gone_dirs and not repo.exists(c):
                    hit = gone_dirs[c]
                if hit:
                    findings.append({
                        "kind": "pr-breaks", "file": af, "line": line_no, "ref": ref,
                        "evidence": {"changed": hit, "moved_to": gone.get(hit)}, "text": line.strip()[:240],
                    })
                    break
    return findings


def describe(f):
    e = f["evidence"]
    if f["kind"] == "moved-or-deleted":
        s = f"`{f['ref']}` is not in the repository. Last removed or renamed in {e['commit']} ({e['date']}): {e['subject']}"
        if e.get("moved_to"):
            s += f". It looks like it moved to `{e['moved_to']}`"
        return s
    if f["kind"] == "missing-script":
        return f"`{f['ref']}`: no package.json in the repository ({e['package_json_files']} checked) defines this script"
    if f["kind"] == "pr-breaks":
        s = f"this change {'renames' if e.get('moved_to') else 'deletes'} `{e['changed']}`"
        if e.get("moved_to"):
            s += f" to `{e['moved_to']}`"
        return s + f", which `{f['file']}` names as `{f['ref']}`"
    return ""


FOOTER = ("This check only proves references against the repository. It cannot see a sentence that names real "
          "things and is still wrong (a function in the wrong role, a dropped option, a rule the code stopped "
          "following). A worked example of that kind of read: https://audit.lesshands.com.au/sample-sentry.html. "
          "Keeping these files true over time: https://audit.lesshands.com.au/offer.html")


def render(findings, nfiles, fmt, repo, footer=True):
    if fmt == "json":
        return json.dumps({"version": VERSION, "agent_files": nfiles, "findings": findings}, indent=2)
    lines = []
    if fmt == "github":
        for f in findings:
            msg = describe(f).replace("%", "%25").replace("\n", " ")
            lines.append(f"::warning file={f['file']},line={f['line']},title=agent-files-check {f['kind']}::{msg}")
        return "\n".join(lines)
    md = fmt == "md"
    head = f"agent-files-check {VERSION}: {nfiles} agent file(s) read, {len(findings)} finding(s)"
    lines.append(f"### {head}" if md else head)
    if repo.shallow:
        lines.append("Note: this is a shallow clone, so history checks see little. Fetch full history for a real read.")
    for f in findings:
        loc = f"{f['file']}:{f['line']}"
        lines.append(f"- **{loc}** ({f['kind']}): {describe(f)}" if md else f"{loc}  [{f['kind']}]  {describe(f)}")
        lines.append(f"  > {f['text']}" if md else f"    {f['text']}")
    if footer:
        lines.append("")
        lines.append(FOOTER)
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agent-files-check", description=__doc__.split("\n\n")[0])
    ap.add_argument("repo", nargs="?", default=".", help="path inside a git checkout (default: .)")
    ap.add_argument("--diff", metavar="BASE...HEAD", help="also report what this change deletes or renames that the instructions name")
    ap.add_argument("--only-diff", action="store_true", help="with --diff, report only pr-breaks findings")
    ap.add_argument("--format", choices=["text", "md", "json", "github"], default="text")
    ap.add_argument("--no-footer", action="store_true")
    ap.add_argument("--experimental-scripts", action="store_true",
                    help="also check npm/pnpm/yarn/bun run scripts (low precision in testing; off by default)")
    ap.add_argument("--fail-on-findings", action="store_true", help="exit 1 when anything is found")
    ap.add_argument("--version", action="version", version=VERSION)
    a = ap.parse_args(argv)
    try:
        repo = Repo(a.repo)
    except RuntimeError as e:
        print(f"agent-files-check: not a git repository: {e}", file=sys.stderr)
        return 2
    files = agent_files(repo)
    findings = []
    if not a.only_diff:
        findings += check_paths(repo, files)
        if a.experimental_scripts:
            findings += check_scripts(repo, files)
    if a.diff:
        findings += check_diff(repo, files, a.diff)
    findings.sort(key=lambda f: (f["file"], f["line"], f["kind"]))
    print(render(findings, len(files), a.format, repo, footer=not a.no_footer and a.format in ("text", "md")))
    return 1 if (a.fail_on_findings and findings) else 0


if __name__ == "__main__":
    sys.exit(main())
