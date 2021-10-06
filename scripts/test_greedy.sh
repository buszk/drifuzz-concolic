#!/bin/bash

concolic_dir=$(dirname $(dirname "$0"))
parallel=0
if [ "$1" == "--parallel" ]; then
    parallel=1
fi

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
    $concolic_dir/snapshot_helper.py $1 &>$concolic_dir/work/$1/snapshot.log
    echo "Explore: $1"
    $concolic_dir/search_greedy.py $1 random_seed &>log/search_greedy.$1.log
    if grep "address: 88," $concolic_dir/work/$1/drifuzz_index >/dev/null; then
        echo "Success: $1"
        [ $2 -eq 1 ] && exit 0
    else
        echo "Fail: $1"
        [ $2 -eq 1 ] && exit 1
    fi
}

num_tests=5
for i in $(seq 0 $((num_tests - 1))); do
    if [ ${parallel} -eq 1 ]; then
        run drifuzz-test-${i} 1 &
    else
        run drifuzz-test-${i} 0
        wait -n
    fi
done

if [ ${parallel} -eq 1 ]; then
    wait_ex
fi
