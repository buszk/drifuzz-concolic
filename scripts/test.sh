#!/bin/bash

concolic_dir=$(dirname $(dirname "$0"))

function wait_ex {
    # this waits for all jobs and returns the exit code of the last failing job
    ecode=0
    while true; do
        [ -z "$(jobs)" ] && break
        wait -n
        err="$?"
        [ "$err" != "0" ] && ecode="$err"
    done
    return $ecode
}

function run {
    echo "Generate snapshot: $1"
    $concolic_dir/snapshot_helper.py $1 &>/dev/null
    echo "Explore: $1"
    $concolic_dir/scripts/run.sh $1 &>/dev/null
    if grep "address: 88," $concolic_dir/work/$1/drifuzz_index >/dev/null; then
        echo "Success: $1"
        exit 0
    else
        echo "Fail: $1"
        exit 1
    fi
}

run drifuzz-test-0 &
run drifuzz-test-1 &
run drifuzz-test-2 &
run drifuzz-test-3 &
run drifuzz-test-4 &

wait_ex
