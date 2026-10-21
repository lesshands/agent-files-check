import json, sys, math
def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k/n; d = 1+z*z/n; c = p+z*z/(2*n); a = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))
    return ((c-a)/d, (c+a)/d)
labels = {}
for lf in sys.argv[2:]:
    rows = json.load(open(lf.replace('labels', 'to-label'))) ; lab = {l['id']: l for l in json.load(open(lf))}
    for r in rows: labels[(r['repo'], r['agent_file'], r['line'], r['reference'])] = lab[r['id']]['label']
f = json.load(open(sys.argv[1])); by = {}
unl = []
for x in f:
    k = (x['repo'], x['file'], x['line'], x['ref']); L = labels.get(k)
    if L is None: unl.append(k); continue
    by.setdefault(x['kind'], []).append(L)
tot = [l for v in by.values() for l in v]
for kind, v in list(by.items()) + [('ALL', tot)]:
    k = v.count('STALE'); n = len([l for l in v if l != 'UNSURE']); lo, hi = wilson(k, n)
    print(f'{kind}: {k}/{n} STALE = {100*k/max(n,1):.0f}% (95% {100*lo:.0f}-{100*hi:.0f}%)')
print('unlabelled', len(unl)); [print(' ', u) for u in unl[:20]]
