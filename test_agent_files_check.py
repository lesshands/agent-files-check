"""Tests for agent_files_check on a throwaway git repository. Run: python3 -m unittest test_agent_files_check"""
import json
import os
import subprocess
import tempfile
import unittest

import agent_files_check as afc


def sh(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"})


def write(repo, path, text):
    p = os.path.join(repo, path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        f.write(text)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = self.repo = self.tmp.name
        sh(r, "init", "-q", "-b", "main")
        write(r, "src/old/helper.ts", "export const a = 1\n")
        write(r, "src/gone.py", "x = 1\n")
        write(r, "lib/keep.go", "package lib\n")
        write(r, "package.json", json.dumps({"scripts": {"test": "x", "lint": "y"}}))
        write(r, ".gitignore", "build/\n")
        write(r, ".github/scripts/check.js", "1\n")
        sh(r, "add", "-A"); sh(r, "commit", "-qm", "start")
        os.makedirs(os.path.join(r, "src/new"), exist_ok=True)
        sh(r, "mv", "src/old/helper.ts", "src/new/helper.ts")
        sh(r, "rm", "-q", "src/gone.py")
        sh(r, "rm", "-q", ".github/scripts/check.js")
        sh(r, "commit", "-qm", "move helper, drop gone")
        write(r, "AGENTS.md", "\n".join([
            "# Agents",
            "Helpers live in `src/old/helper.ts`.",           # 2 moved -> finding with moved_to
            "Entry point is `src/gone.py`.",                  # 3 deleted -> finding
            "Go code in `lib/keep.go`.",                      # 4 exists -> nothing
            "Output goes to `build/out.js`.",                 # 5 gitignored -> nothing
            "Uses `react-dom/client` and `.tsx` files.",       # 6 package / ext-only -> nothing
            "Config at `config/never-was.yaml`.",              # 7 never tracked -> nothing (unproven)
            "We removed `src/gone.py` last week.",             # 8 accurate absence -> nothing
            "Run `npm run test` then `pnpm run typecheck`.",   # 9 typecheck missing -> finding
            "```", "`src/gone.py` inside a fence", "```",      # fenced -> nothing
            "CI runs `.github/scripts/check.js`.",            # 13 dot-folder path deleted -> finding
        ]) + "\n")
        sh(r, "add", "-A"); sh(r, "commit", "-qm", "agents file")

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, *extra):
        repo = afc.Repo(self.repo)
        files = afc.agent_files(repo)
        f = afc.check_paths(repo, files) + afc.check_scripts(repo, files)
        if extra:
            f += afc.check_diff(repo, files, extra[0])
        return files, f

    def test_discovers_agent_file(self):
        files, _ = self.run_check()
        self.assertEqual(files, ["AGENTS.md"])

    def test_findings_are_exactly_the_proven_ones(self):
        _, f = self.run_check()
        got = sorted((x["line"], x["kind"], x["ref"]) for x in f)
        self.assertEqual(got, [(2, "moved-or-deleted", "src/old/helper.ts"),
                               (3, "moved-or-deleted", "src/gone.py"),
                               (9, "missing-script", "pnpm run typecheck"),
                               (13, "moved-or-deleted", ".github/scripts/check.js")])
        moved = [x for x in f if x["ref"] == "src/old/helper.ts"][0]
        self.assertEqual(moved["evidence"]["moved_to"], "src/new/helper.ts")

    def test_diff_mode_names_sentence_a_change_breaks(self):
        r = self.repo
        sh(r, "checkout", "-qb", "feature")
        sh(r, "rm", "-q", "lib/keep.go")
        sh(r, "commit", "-qm", "drop keep")
        _, f = self.run_check("main...feature")
        pr = [x for x in f if x["kind"] == "pr-breaks"]
        self.assertEqual([(x["line"], x["ref"]) for x in pr], [(4, "lib/keep.go")])

    def test_cli_formats(self):
        for fmt in ("text", "md", "json", "github"):  # scripts are opt-in
            out = subprocess.run(["python3", afc.__file__, self.repo, "--format", fmt],
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("src/gone.py", out.stdout)
        rc = subprocess.run(["python3", afc.__file__, self.repo, "--fail-on-findings"], capture_output=True).returncode
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
