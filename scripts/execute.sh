#!/bin/bash

if [ $# != 1 ]; then
    echo "$0 <target>"
    exit
fi
target=$1
#cp work/$target/out/0 tmp
./concolic.py $target tmp 2>&1 |tee -i log/cl
