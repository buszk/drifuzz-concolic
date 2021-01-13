#!/bin/bash

modprobe $1
cat /proc/modules
sleep 0.2
