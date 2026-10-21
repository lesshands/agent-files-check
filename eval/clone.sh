#!/bin/bash
# clone.sh OWNER/REPO [SHA]: blobless full-history clone, read-only use
r=$1; d=${AFC_WORK:-$(dirname "$0")/work}/repos/${r//\//__}
[ -d "$d/.git" ] && exit 0
GIT_TERMINAL_PROMPT=0 git -c core.hooksPath=/dev/null clone -q --filter=blob:none --no-checkout https://github.com/$r.git "$d" 2>>"${AFC_WORK:-$(dirname "$0")/work}/clone.err" || { echo "FAIL $r"; exit 0; }
cd "$d" && git -c core.hooksPath=/dev/null checkout -q ${2:-HEAD} 2>>"${AFC_WORK:-$(dirname "$0")/work}/clone.err" && echo "OK $r"
