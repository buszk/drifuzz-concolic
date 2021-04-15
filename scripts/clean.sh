#!/bin/bash

if [ $# != 1 ]; then
    echo "$0 <target>"
    exit
fi
target=$1
rm -f work/$target/$target.sav
rm -f work/$target/search.sav
