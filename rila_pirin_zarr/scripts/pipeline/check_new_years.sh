#!/usr/bin/env bash
# Run check_year.py on every finished year of a series that has no check yet; repeat until all years are checked.
# Inside the container, cd /app:
#   bash rila_pirin_zarr/scripts/pipeline/check_new_years.sh v2 1940 2025 >> rila_pirin_zarr/data/logs/check_v2/loop.log 2>&1
# One SUMMARY line per year goes to data/logs/check_<series>/summary.log (ALL PASS / FAILED).
set -uo pipefail
R=rila_pirin_zarr
V=${1:?series v1|v2}; Y0=${2:?first year}; Y1=${3:?last year}
RUNS=$R/data/runs; [ "$V" = v2 ] && RUNS=$R/data/runs_v2
L=$R/data/logs/check_$V; mkdir -p $L
while true; do
  left=0
  for Y in $(seq $Y0 $Y1); do
    [ -f $L/check_$Y.txt ] && continue
    left=1
    [ -f $RUNS/$Y/DONE ] || continue
    python $R/scripts/pipeline/check_year.py $Y --series $V 2>&1 | grep '^SUMMARY' >> $L/summary.log
  done
  [ $left -eq 0 ] && break
  sleep 300
done
echo "all $V years checked: $(grep -c 'ALL PASS' $L/summary.log) pass, $(grep -c 'FAILED' $L/summary.log) failed" >> $L/summary.log
