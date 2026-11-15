# surfex_crocus/ – copy of ~/SurfexCrocus (SURFEX-Crocus setup, analysis and aspect-fix work)

Copied into this repository on 15 Nov 2026 so the Crocus part of the workflow is versioned with the downscaling.
The working copy that the running pipeline uses is still `~/SurfexCrocus` (paths in
`meridionali_zarr/scripts/crocus_all_hy.sh` point there). Re-sync before committing:

    rsync -a --exclude 'aspect_fix/TopoPyScale_fix/' --exclude 'subset_hourly/' --exclude '*.nc' --exclude '*.pck' \
          --exclude '*.pkl' --exclude '__pycache__/' --exclude 'gmon.out' ~/SurfexCrocus/ meridionali_zarr/surfex_crocus/

Not copied: model runs (`subset_hourly/`, all `*.nc`), pickled tables, and `aspect_fix/TopoPyScale_fix/` (a git
worktree of TopoPyScale; that code is in the TopoPyScale repository, branch fix/aspect-azimuth-convention).

| Path | What |
|---|---|
| `README.md`, `LOG.md` | Crocus HY 2024-25 test and aspect-fix work log |
| `scripts/` | `common.py`, `crocus_hy_analysis.py`, `compare_old_new.py`, `run_subset_hourly.py` (+ v1 backups) |
| `aspect_fix/CHANGELOG_aspect_fix.md` | what was wrong, the fix commits, how it was tested |
| `aspect_fix/scripts/` | `crocus_parallel_nam.py` (Crocus runner used by crocus_all_hy.sh), diagnosis/check scripts |
| `aspect_fix/namelists/` | `OPTIONS_3hourly_full.nam` (current runs), `OPTIONS_hourly_*.nam` |
| `aspect_fix/checks/`, `aspect_fix/config/`, `aspect_fix/logs/` | check results, fix-run configs, run logs |
| `hy2024-2025*/` | HY 2024-25 indicator tables and figures (old, old relabelled, fixed) |
