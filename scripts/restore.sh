#!/bin/bash

if [ $# != 1 ]; then
    echo "$0 <target>"
    exit
fi
target=$1
cp work/$target/$target.sav.bk work/$target/$target.sav
cp work/$target/search.sav.bk work/$target/search.sav
