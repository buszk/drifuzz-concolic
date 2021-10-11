#!/bin/bash

if [ $# != 1 ]; then
    echo "$0 <target>"
    exit
fi
mkdir -p log
target=$1
time ./search_greedy.py $target random_seed 2>&1|tee -i log/search_greedy.$target.log
