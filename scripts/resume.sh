#!/bin/bash

if [ $# != 1 ]; then
    echo "$0 <target>"
    exit
fi
target=$1
time ./search_group.py --resume $target random_seed 2>&1|tee -i log/search_group.$target.resume.log
