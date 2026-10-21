"""Run agent_files_check over cloned repos; write findings.json. Tune set also scored against the 60 old labels."""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); WORK = os.environ.get('AFC_WORK', os.path.join(HERE, 'work'))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import agent_files_check as afc
which = sys.argv[1]  # tune | heldout
repos = [l.split()[0] for l in open(f'{which}.txt') if l.strip()]
out = []
for r in repos:
    d = os.path.join(WORK, 'repos', r.replace('/', '__'))
    if not os.path.isdir(d + '/.git'):
        print('MISSING', r); continue
    t = time.time()
    try:
        repo = afc.Repo(d); files = afc.agent_files(repo)
        f = afc.check_paths(repo, files)
    except Exception as e:
        print('ERR', r, e); continue
    head = afc.git(d, 'rev-parse', 'HEAD').strip()
    for x in f: x['repo'] = r; x['sha'] = head
    out += f
    print(f'{r}: {len(files)} files, {len(f)} findings, {time.time()-t:.1f}s', flush=True)
json.dump(out, open(f'findings-{which}.json', 'w'), indent=1)
if which == 'tune':
    labels = json.load(open(os.path.join(HERE, 'scan-labels-60.json')))
    rows = labels if isinstance(labels, list) else labels.get('rows', labels)
    hit = {(x['repo'], x['file'], x['line']) for x in out}
    hitref = {(x['repo'], x['file'], x['ref']) for x in out}
    for row in rows:
        k = (row['repo'], row['file'], row['line'])
        flagged = k in hit or (row['repo'], row['file'], row['ref']) in hitref
        print(row.get('label'), 'FLAGGED' if flagged else '-', row['repo'], row['file'], row['line'], row['ref'])
print('total findings', len(out))
