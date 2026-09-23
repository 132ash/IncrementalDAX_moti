#!/usr/bin/env bash
set -euo pipefail

if (($# < 5 || $# > 6)); then
  echo "usage: $0 OUTPUT_TSV PHASE_FILE INTERVAL_SECONDS CGROUP_DIR COMM_GLOB [MIN_RSS_KIB]" >&2
  exit 2
fi

output=$1
phase_file=$2
interval=$3
cgroup_dir=$4
comm_glob=$5
min_rss_kib=${6:-32768}

test -r "$cgroup_dir/memory.current"
test -r "$cgroup_dir/memory.stat"

printf '%s\n' \
  $'timestamp_ns\tphase\tcgroup_current_bytes\tcgroup_anon_bytes\tcgroup_file_bytes\tcgroup_kernel_bytes\tvmm_count\tvmm_rss_kib\tvmm_pss_kib\tvmm_pss_anon_kib\tvmm_pss_file_kib\tvmm_private_dirty_kib\tvmm_shared_clean_kib' \
  > "$output"

while :; do
  [[ -r $cgroup_dir/memory.current && -r $cgroup_dir/memory.stat ]] || exit 0
  timestamp_ns="$(date +%s%N)"
  phase="$(cat "$phase_file" 2>/dev/null || printf unknown)"
  current="$(cat "$cgroup_dir/memory.current")"
  read -r anon file kernel < <(
    awk '
      $1 == "anon" { anon=$2 }
      $1 == "file" { file=$2 }
      $1 == "kernel" { kernel=$2 }
      END { printf "%s %s %s\n", anon+0, file+0, kernel+0 }
    ' "$cgroup_dir/memory.stat"
  )

  count=0 rss_total=0 pss_total=0 pss_anon_total=0 pss_file_total=0
  private_dirty_total=0 shared_clean_total=0
  declare -A seen=()
  while read -r pid; do
    [[ $pid =~ ^[0-9]+$ ]] || continue
    [[ -z ${seen[$pid]+x} ]] || continue
    seen[$pid]=1
    comm="$(cat "/proc/$pid/comm" 2>/dev/null || true)"
    case "$comm" in
      $comm_glob) ;;
      *) continue ;;
    esac
    quick_rss="$(awk '$1 == "VmRSS:" { print $2; found=1; exit } END { if (!found) print 0 }' "/proc/$pid/status" 2>/dev/null || printf 0)"
    ((quick_rss >= min_rss_kib)) || continue
    rollup="$(sudo -n awk '
      $1 == "Rss:" { rss=$2 }
      $1 == "Pss:" { pss=$2 }
      $1 == "Pss_Anon:" { pss_anon=$2 }
      $1 == "Pss_File:" { pss_file=$2 }
      $1 == "Private_Dirty:" { private_dirty=$2 }
      $1 == "Shared_Clean:" { shared_clean=$2 }
      END { printf "%s %s %s %s %s %s\n", rss+0, pss+0, pss_anon+0, pss_file+0, private_dirty+0, shared_clean+0 }
    ' "/proc/$pid/smaps_rollup" 2>/dev/null || printf '0 0 0 0 0 0')"
    read -r rss pss pss_anon pss_file private_dirty shared_clean <<< "$rollup"
    count=$((count + 1))
    rss_total=$((rss_total + rss))
    pss_total=$((pss_total + pss))
    pss_anon_total=$((pss_anon_total + pss_anon))
    pss_file_total=$((pss_file_total + pss_file))
    private_dirty_total=$((private_dirty_total + private_dirty))
    shared_clean_total=$((shared_clean_total + shared_clean))
  done < <(
    find "$cgroup_dir" -name cgroup.procs -type f -exec cat {} + 2>/dev/null || true
    if [[ ${HOST_INCLUDE_ALL_MATCHING_VMM:-0} == 1 ]]; then
      pgrep -x cloud-hyperviso || true
    fi
  )
  unset seen

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$timestamp_ns" "$phase" "$current" "$anon" "$file" "$kernel" \
    "$count" "$rss_total" "$pss_total" "$pss_anon_total" "$pss_file_total" \
    "$private_dirty_total" "$shared_clean_total" >> "$output"
  sleep "$interval"
done
