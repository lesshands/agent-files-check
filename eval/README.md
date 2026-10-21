# Evaluation data and scripts

- `tune.txt` (repo, commit) and `heldoutall.txt`: the 35 tuning and 45 held-out repositories (see ../SCORE.md).
- `findings-*.json`: what the tool reported. `to-label-*.json` + `labels-*.json`: each finding and its hand label.
- `scan-labels-60.json`: the 60 labelled hits of the earlier plain path scan, used for tuning.
- `replay-final.json`: the pull-request replay.

Rerun (needs git and network; full-history clones are large, several GB in total):

```
export AFC_WORK=$PWD/work; mkdir -p $AFC_WORK
cat tune.txt | xargs -P 8 -L 1 ./clone.sh          # tuning repos at the measured commits
awk '{print $1}' heldoutall.txt | xargs -P 8 -L 1 ./clone.sh
python3 run_eval.py heldoutall                       # writes findings-heldoutall.json
python3 score.py findings-heldoutall.json labels-2.json
```

Held-out repositories were cloned at their default branch on 21 Oct 2026; a rerun later sees newer commits.
