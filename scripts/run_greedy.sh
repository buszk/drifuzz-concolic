#!/bin/bash

USB_ARG=
while :; do
    case $1 in
        --usb)
            USB_ARG=$1
            shift
        ;;
        *)
            break
    esac
done

if [ $# != 1 ]; then
    echo "$0 <target>"
    exit
fi
target=$1
if [ -d "work/$target" ]; then
    mkdir -p log
    time ./search_greedy.py $USB_ARG $target random_seed 2>&1|tee -i log/search_greedy.$target.log
fi
