#/bin/bash
if [ "$#" -ne 1 ]; then
	echo "$0 <target>"
	exit 1
fi
target=$1
grep key ../drifuzz-concolic/work/${target}/search.sav |awk '{print $2}' |sed 's/,//g'|sort|uniq |xargs -I '{}' ./addr2line.py ${target} '{}' |grep -v module_ |grep -v addr2line|less
