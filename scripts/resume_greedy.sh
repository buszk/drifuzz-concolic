#!/bin/bash

if [ $# != 1 ]; then
    echo "$0 <target>"
    exit
fi
target=$1
time ./search_greedy.py --resume $target random_seed 2>&1|tee -i log/search_greedy.$target.resume.log
