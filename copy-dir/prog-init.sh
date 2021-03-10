#!/bin/bash

modprobe $1
if ip link | grep "eth0"; then
ip link set dev eth0 up
elif ip link | grep "wlan0"; then
ip link set dev wlan0 up
fi
cat /proc/modules
sleep 1
