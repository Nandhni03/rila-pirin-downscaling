#!/bin/bash
# Part 3.3 + 4 of the aspect fix (11 Nov 2026): Crocus HY 2024-25 with the FIXED forcing, then old vs new.
# Same setup as the old runs; only the forcing differs (TopoPyScale branch fix/aspect-azimuth-convention, runs Efix2).
# Every step writes to NEW folders; nothing old is overwritten. Stops at the first failing step.
# Log: ~/SurfexCrocus/aspect_fix/logs/comparison_2024-25.log
set -u
FIX=$HOME/SurfexCrocus/aspect_fix
MZ=$HOME/TopoPyScale-repo-github/downscaling/meridionali_zarr
PY=$HOME/TopoPyScale-repo-github/venv/bin/python
FORCING=$MZ/data/surfex_Efix/FORCING_2024090100_2025083123.nc

step() {   # step <name> <command...>
  echo "=== $(date '+%F %T') START $1"
  shift; "$@"; rc=$?
  echo "=== $(date '+%F %T') exit $rc"
  [ $rc -eq 0 ] || { echo "FAILED, stopping"; exit 1; }
}

cd $HOME/TopoPyScale-repo-github/downscaling

# 1. SURFEX forcing from the fixed stores, exported with the fix branch (its to_surfex writes aspect from north)
step "1 export forcing (fix branch)" env PYTHONPATH=$FIX/TopoPyScale_fix $PY meridionali_zarr/scripts/export_surfex.py \
  $FIX/config/config_meridionali_Efix2_2024-09_2024-12.yml $FIX/config/config_meridionali_Efix2_2025-01_2025-08.yml \
  --start 2024-09-01 --end 2025-08-31 --out $MZ/data/surfex_Efix

# 2. All 3001 points, 6-hourly, default snowtools options (as data/crocus_E/2024-2025)
step "2 crocus all points 6-hourly" $PY $FIX/scripts/crocus_parallel_nam.py $FORCING \
  --out $MZ/data/crocus_Efix/2024-2025 --chunks 12 --parallel 12

# 3. All points, hourly, reduced output (HS/SWE/LWC) for wet-snow days (as data/crocus_E/2024-2025_hourly_reduced)
step "3 crocus all points hourly reduced" $PY $FIX/scripts/crocus_parallel_nam.py $FORCING \
  --out $MZ/data/crocus_Efix/2024-2025_hourly_reduced --chunks 12 --parallel 12 \
  --namelist $FIX/namelists/OPTIONS_hourly_reduced.nam

cd $HOME/SurfexCrocus
# 4. 24-point hourly subset with full profiles (same points as the old variant)
step "4 subset hourly profiles" $PY scripts/run_subset_hourly.py fix
# 5. Indicators/figures for the fix variant, then old vs new
step "5a analysis fix" $PY scripts/crocus_hy_analysis.py fix
step "5b compare old vs new" $PY scripts/compare_old_new.py
echo "ALL DONE $(date '+%F %T')"
