#!/bin/bash
# TopoSCALE at the station points (validation step 3), one year after the other. Inside the container:
#   docker exec -i toposcale-rila-pirin bash -s <v1|v2> Y0 Y1 < rila_pirin_zarr/scripts/validation/run_points.sh
#   (or, from /app:  bash rila_pirin_zarr/scripts/validation/run_points.sh v2 1959 2025)
# v1 = config/points    -> data/points/runs     (fork tag rila-pirin-ncar-v1)
# v2 = config/points_v2 -> data/points/runs_v2  (fork branch integrate-fixes, LOG.md 2026-11-15)
# Configs: scripts/validation/points_setup.py. A year with 12 month files is skipped (resumable).
V=${1:?v1 or v2}; Y0=${2:?first year}; Y1=${3:?last year}
cd /app
R=rila_pirin_zarr
case $V in
  v1) C=$R/config/points;    L=$R/data/points/logs;    O=$R/data/points/runs ;;
  v2) C=$R/config/points_v2; L=$R/data/points/logs_v2; O=$R/data/points/runs_v2 ;;
  *) echo "unknown variant $V"; exit 2 ;;
esac
mkdir -p $L
for Y in $(seq $Y0 $Y1); do
  n=$(ls $O/$Y/outputs/months/*.json 2>/dev/null | wc -l)
  [ "$n" -ge 12 ] && { echo "$V $Y already done"; continue; }
  t0=$(date +%s)
  python $R/scripts/pipeline/run_year.py $C/config_points_$Y.yml --terrain $R/data/points/terrain \
      --months 1 2 3 4 5 6 7 8 9 10 11 12 > $L/run_$Y.log 2>&1
  rc=$?
  echo "$(date -u +%H:%M) $V $Y exit $rc, $(( $(date +%s) - t0 )) s, months $(ls $O/$Y/outputs/months/*.json 2>/dev/null | wc -l)"
done
echo "$V all done"
