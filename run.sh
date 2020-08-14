#!/bin/bash

DRIFUZZ=$HOME/Workspace/git/Drifuzz
PANDA_BUILD=$HOME/Workspace/git/panda-build
target=alx
#gdb -ex "r"  --args \
$PANDA_BUILD/x86_64-softmmu/panda-system-x86_64 \
    -kernel $DRIFUZZ/linux-module-build/arch/x86_64/boot/bzImage \
    -append "console=ttyS0 nokaslr root=/dev/sda earlyprintk=serial" \
    buster.qcow2 \
    -m 1G \
    -nographic \
    -no-acpi \
    -device drifuzz \
    -net user -net nic,model=$target \
    #-loadvm ${target}_root
