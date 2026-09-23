#!/usr/bin/env bash
set -euo pipefail

if (($# < 4 || $# > 5)); then
  echo "usage: $0 OUTPUT_TSV PHASE CGROUP_DIR COMM_GLOB [MIN_RSS_KIB]" >&2
  exit 2
fi

output=$1
phase=$2
cgroup_dir=$3
comm_glob=$4
min_rss_kib=${5:-32768}
timestamp_ns="$(date +%s%N)"

if [[ ! -e $output ]]; then
  printf '%s\n' $'timestamp_ns\tphase\tpid\tcomm\taddress\tperms\tpathname\tsize_kib\trss_kib\tpss_kib\tshared_clean_kib\tshared_dirty_kib\tprivate_clean_kib\tprivate_dirty_kib\tanonymous_kib' > "$output"
fi

declare -A seen=()
while read -r pid; do
  [[ $pid =~ ^[0-9]+$ ]] || continue
  [[ -z ${seen[$pid]+x} ]] || continue
  seen[$pid]=1
  comm="$(cat "/proc/$pid/comm" 2>/dev/null || true)"
  case "$comm" in $comm_glob) ;; *) continue ;; esac
  quick_rss="$(awk '$1 == "VmRSS:" { print $2; found=1; exit } END { if (!found) print 0 }' "/proc/$pid/status" 2>/dev/null || printf 0)"
  ((quick_rss >= min_rss_kib)) || continue
  sudo -n awk -v ts="$timestamp_ns" -v phase="$phase" -v pid="$pid" -v comm="$comm" '
    function emit() {
      if (address != "") printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n", ts,phase,pid,comm,address,perms,path,size,rss,pss,shared_clean,shared_dirty,private_clean,private_dirty,anonymous
    }
    /^[0-9a-f]+-[0-9a-f]+ / {
      emit(); address=$1; perms=$2; path=""; for (i=6; i<=NF; i++) path=path (path=="" ? "" : " ") $i
      size=rss=pss=shared_clean=shared_dirty=private_clean=private_dirty=anonymous=0; next
    }
    $1 == "Size:" { size=$2 }
    $1 == "Rss:" { rss=$2 }
    $1 == "Pss:" { pss=$2 }
    $1 == "Shared_Clean:" { shared_clean=$2 }
    $1 == "Shared_Dirty:" { shared_dirty=$2 }
    $1 == "Private_Clean:" { private_clean=$2 }
    $1 == "Private_Dirty:" { private_dirty=$2 }
    $1 == "Anonymous:" { anonymous=$2 }
    END { emit() }
  ' "/proc/$pid/smaps" >> "$output"
done < <(find "$cgroup_dir" -name cgroup.procs -type f -exec cat {} + 2>/dev/null || true)
