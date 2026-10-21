"""PR-mode replay: for each moved-or-deleted finding, check out the deleting commit in a temporary worktree and run
--diff <commit>^...<commit> --only-diff. Hit = the same agent file and reference flagged as pr-breaks."""
import json, os, subprocess, sys, tempfile
WORK = os.environ.get('AFC_WORK', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'work'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import agent_files_check as afc
rows = json.load(open(sys.argv[1])); out = []
for x in rows:
    if x['kind'] != 'moved-or-deleted': continue
    d = os.path.join(WORK, 'repos', x['repo'].replace('/', '__')); sha = x['evidence']['commit']
    wt = tempfile.mkdtemp(prefix='afc-wt-', dir=WORK)
    try:
        subprocess.run(['git', '-C', d, '-c', 'core.hooksPath=/dev/null', 'worktree', 'add', '-q', '--detach', wt, sha], check=True, capture_output=True)
        repo = afc.Repo(wt); files = afc.agent_files(repo)
        f = afc.check_diff(repo, files, f'{sha}^...{sha}')
        hit = any(y['file'] == x['file'] and y['ref'] == x['ref'] for y in f)
        named_then = os.path.exists(os.path.join(wt, x['file'])) and x['ref'] in open(os.path.join(wt, x['file']), errors='replace').read()
        out.append({**x, 'replay_hit': hit, 'named_at_deletion': named_then, 'replay_findings': len(f)})
        print(x['repo'], x['file'], x['ref'], 'named-then' if named_then else 'not-named-then', 'HIT' if hit else 'miss', flush=True)
    except subprocess.CalledProcessError as e:
        print('ERR', x['repo'], e.stderr[:200])
    finally:
        subprocess.run(['git', '-C', d, 'worktree', 'remove', '--force', wt], capture_output=True)
json.dump(out, open(sys.argv[2], 'w'), indent=1)
named = [r for r in out if r['named_at_deletion']]
print('replayed', len(out), 'named at deletion', len(named), 'flagged', sum(r['replay_hit'] for r in named))
