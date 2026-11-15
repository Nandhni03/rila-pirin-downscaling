#!/bin/bash
# 15 Nov 2026 (user: "after it finishes the current running year from cds, I wouldn't use it, only as last resort").
# Waits until the running driver has downloaded AND downscaled 2008, then stops it (and the CDS downloader it started
# for the next year) and restarts the driver with NO_CDS=1 for 2007..1940: no CDS downloads, only the downscaling lane,
# which downscales every year the NCAR lanes complete (verified + COMPLETE marker), with the fixed TopoPyScale.
#   cd ~/TopoPyScale-repo-github/downscaling
#   setsid nohup meridionali_zarr/scripts/cds_off_after_2008.sh <driver pid> <driver output> > meridionali_zarr/data/logs/overnight_E/cds_off_after_2008.out 2>&1 < /dev/null &
set -u
cd $HOME/TopoPyScale-repo-github/downscaling
PID=$1; OUT=$2
until grep -q '\*\*2008 DONE\*\*\|2008 downscaling FAILED' $OUT; do sleep 60; done
grep -q '2008 downscaling FAILED' $OUT && { echo "$(date '+%F %T') 2008 downscaling failed: driver left running, nothing changed"; exit 1; }
echo "$(date '+%F %T') 2008 done; stopping driver $PID and any CDS downloader"
kill $PID; sleep 10
for p in $(ps -eo pid,args | awk '$0 ~ /era5_download\.py .*config\/era5\/config_era5_meridionali_[0-9]+_cds\.yml/ && $0 !~ /awk/ {print $1}'); do kill $p; done
sleep 5
NO_CDS=1 CDS_ONLY=1 OVERNIGHT_LOG=LOG_28Oct2026.md setsid nohup ../venv/bin/python meridionali_zarr/scripts/overnight_E.py \
    $(seq 2007 -1 1940) > meridionali_zarr/data/logs/overnight_E/driver_v5e_nocds.out 2>&1 < /dev/null &
echo "$(date '+%F %T') driver restarted without CDS (pid $!), years 2007..1940 -> data/logs/overnight_E/driver_v5e_nocds.out"
echo "- $(date '+%H:%M:%S') [cds-off] 2008 downloaded (CDS) and downscaled; CDS lane switched off (NO_CDS=1, last resort only). Driver restarted for downscaling only, years 2007..1940 (pid $!)" >> meridionali_zarr/LOG_28Oct2026.md
