#!/bin/bash
# Downscaling with the fix branch for the given run names. Log: aspect_fix/logs/downscale_<name>.log
set -u
FIX=$HOME/SurfexCrocus/aspect_fix
export PYTHONPATH=$FIX/TopoPyScale_fix
cd $HOME/TopoPyScale-repo-github/downscaling
for name in "$@"; do
  log=$FIX/logs/downscale_$name.log
  { echo "start $(date '+%F %T'); branch $(git -C $PYTHONPATH rev-parse --abbrev-ref HEAD) $(git -C $PYTHONPATH rev-parse --short HEAD)"
    ../venv/bin/python -c "import TopoPyScale; print('TopoPyScale imported from', TopoPyScale.__file__)"
    /usr/bin/time -v ../venv/bin/python meridionali_zarr/scripts/run_year_public.py $FIX/config/config_$name.yml --stop-after downscale
    echo "exit $? end $(date '+%F %T')"; } > $log 2>&1
  grep -q "^exit 0" $log || { echo "FAILED $name"; exit 1; }
done
echo ALL DONE
