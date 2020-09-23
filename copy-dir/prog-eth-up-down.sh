#!/bin/bash

modprobe $1
ip link set dev eth0 up
ip link set dev eth0 down
rmmod $1