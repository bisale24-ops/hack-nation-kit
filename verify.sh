#!/usr/bin/env bash
# Everything the kit claims, proved on this machine. Run it whenever the kit changes.
# Six checks must pass; three must fail on purpose, which is what makes the other six mean
# anything. Exits non-zero if any of that stops being true.
H=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
pass=0; fail=0
run() { desc=$1; shift; if "$@" >$work/last.log 2>&1; then echo "PASS  $desc"; pass=$((pass+1));
        else echo "FAIL  $desc (exit $?)"; tail -4 $work/last.log; fail=$((fail+1)); fi; }
runfail() { desc=$1; shift; if "$@" >$work/last.log 2>&1; then echo "FAIL  $desc — it should have failed"; fail=$((fail+1));
        else echo "PASS  $desc"; pass=$((pass+1)); fi; }

run "kit gate green"                 "$H/kit/check.sh"
run "preflight green"                "$H/kit/preflight.sh" --gate
rm -rf $work/fresh
run "new.sh stamps a green project"  env TARGET=$work/fresh "$H/kit/new.sh" fresh "one line"
run "stamped project's own gate"     bash -c "cd $work/fresh && ./check.sh"
run "publish dry run on it"          bash -c "cd $work/fresh && DRY_RUN=1 $H/kit/publish.sh"
# Assembled at run time rather than written out, so this file is not itself a key-shaped string.
prefix=sk-ant
runfail "publish refuses a key"      bash -c "cd $work/fresh && echo 'K=\"$prefix-api03-AAAAAAAAAAAAAAAAAAAAAAAAAA\"' > l.py && git add l.py && DRY_RUN=1 $H/kit/publish.sh"
run "clean that up"                  bash -c "cd $work/fresh && git rm -q --cached l.py && rm l.py"
run "video length report"            bash -c "$HOME/.venvs/video/bin/python $H/kit/video/render.py $H/kit/video/smoke/script.py --length-only"
runfail "video over the limit fails" bash -c "$HOME/.venvs/video/bin/python $H/kit/video/render.py $H/kit/video/smoke/script.py --length-only --max-seconds 5"
run "smoke video is h264+aac 720p"   bash -c "ffprobe -v error -show_entries stream=codec_name,height -of csv=p=0 $H/kit/video/smoke/smoke.mp4 | grep -q '^h264,720$' && ffprobe -v error -show_entries stream=codec_name -of csv=p=0 $H/kit/video/smoke/smoke.mp4 | grep -q aac"
runfail "no credentials in the kit"  bash -c "cd $H && git ls-files -z | xargs -0 grep -lEI -e 'sk-ant-[A-Za-z0-9_-]{20,}' -e 'gh[pousr]_[A-Za-z0-9]{30,}' -e 'AKIA[0-9A-Z]{16}'"
echo; echo "$pass passed, $fail failed"; exit $((fail > 0))
