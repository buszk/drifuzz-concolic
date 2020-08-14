#!/bin/bash

DRIFUZZ=$HOME/Workspace/git/Drifuzz
PANDA_BUILD=$HOME/Workspace/git/panda-build

#gdb \
#    -ex 'handle SIGUSR1 noprint' \
#    -ex 'r' \
#    --args \
$PANDA_BUILD/x86_64-softmmu/panda-system-x86_64 \
    -kernel $DRIFUZZ/linux-module-build/arch/x86_64/boot/bzImage \
    -append "console=ttyS0 nokaslr root=/dev/sda earlyprintk=serial" \
    -m 1G \
    -nographic \
    -replay alx \
    -panda tainted_mmio \
    -panda tainted_branch \
    -pandalog alx.plog \
    -net user -net nic,model=alx \
    -device drifuzz

    #-no-acpi \


