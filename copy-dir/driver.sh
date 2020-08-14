#!/bin/sh
rmmod e1000
modprobe e1000
ip link set enp0s3 up
