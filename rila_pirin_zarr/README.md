# rila_pirin_zarr: Rila-Pirin climate downscaling 1940-2025 (FABDEM 30 m, ERA5 14 levels, TopoPyScale)

ERA5 (14 pressure levels 600-1000 hPa + single levels) -> TopoSUB (1002 clusters in 4 elevation groups) ->
TopoSCALE (`topo_scale_zarr`, our TopoPyScale fork), one hourly Zarr store per year plus daily statistics, and a
station validation of temperature. Every decision, run and result with its date and reason: **`LOG.md`**.
Runs inside the Docker container (`docker compose up -d` in the repo root, then `docker exec -it toposcale-rila-pirin bash`, `cd /app`).

## Where are the results? -> `results/`

```
results/STATUS.md            every year x series (done / downscaling / queued), refreshed every 10 min
results/ncar_v2/YYYY/        FINAL series (links into data/runs_v2/YYYY/outputs)
results/ncar_v2/t_mean_monthly/   t_mean_monthly_YYYY.tif, 12 bands, all years in one folder (QGIS)
results/ncar_v1/...          the first series of the same input, unfixed code; kept for comparison only
results/qgis_examples/       a few small GeoTIFFs to look at in QGIS (lapse-adjusted months, v2 - v1 differences)
```
Each `YYYY/` holds `downscaled/down.zarr` (hourly: t, p, q, u, v, w, ws, wd, SW, SW_direct, SW_diffuse, LW, tp),
`downscaled/daily.zarr` (daily statistics), `geotiff/t_mean_monthly_YYYY.tif`, `year_summary.json`, `months/*.json`.

### Series
| series | code | status |
|---|---|---|
| **NCAR v2** (`data/runs_v2`, `config/years_v2`) | TopoPyScale fork, branch `integrate-fixes` | **final**; 1940-2025 complete 2026-11-16, 86/86 checks pass |
| NCAR v1 (`data/runs`, `config/years`) | fork tag `rila-pirin-ncar-v1` | 1940-2025 complete; superseded by v2 |
| EDH, 5 levels (`data/runs_edh`, `config/years_edh`) | fork tag `rila-pirin-ncar-v1` | **dropped 2026-11-15** (fewer levels, slightly worse); kept on disk until v2 is checked |

v2 = v1 + three fixes (LOG.md 2026-11-15): direct SW capped at the top-of-atmosphere value (no sunset spikes);
sun position at the middle of each ERA5 hour (removes the W > E bias); below-1000-hPa fallback decided per time
step (low clusters no longer depend on the period run); solar geometry cache stored unpacked.

## Setup (decided 2026-11-05; tests behind each choice in LOG.md)

| | |
|---|---|
| DEM | FABDEM V1-2, 30 m, EPSG:32634 (4233 x 3998 px), rectangle mask 9,686,304 px |
| clusters | k = 1000 in groups <800 / 800-1500 / 1500-2000 / >=2000 m, density coefficients 0.5 / 1 / 1.5 / 2 -> 149 / 427 / 241 / 185 |
| features | x 1, y 1, elevation 6, slope 1, aspect_cos 2, aspect_sin 2, svf 1; minibatch k-means, seed 2 |
| centroid aspect | circular mean atan2(sin, cos). Aspect convention 0 = south, + towards east (verified 2026-11-15). The fork's arithmetic mean wraps at south (kept as `aspect_arith`) |
| ERA5 | pressure levels: NCAR d633000 NCSS, 600-1000 hPa (14 levels); 7 single-level variables: CDS (NCAR for a few years); 1940-2025. 1940-01-01 00-06 UTC accumulations filled (ERA5 has none) |
| products | `down.zarr` (hourly), `daily.zarr` (daily stats), `t_mean_monthly_YYYY.tif` (12 bands, viewing only) |

## Folder

```
README.md, LOG.md                  this file; the full log of decisions and results
config/
  config_terrain.yml               terrain + clusters + horizon (once)
  era5/config_era5_YYYY.yml        one year of ERA5 (zarr_workflow/era5_download/era5_download.py)
  years_v2/config_YYYY.yml         one year of downscaling, v2 (final)   -> data/runs_v2/YYYY
  years/config_YYYY.yml            the same, v1                          -> data/runs/YYYY
  points_v2/, points/              station point runs (validation), v2 / v1 -> data/points/runs_v2, runs
  years_edh/                       dropped EDH series (history)
scripts/
  pipeline/                        making the dataset
    make_configs.py                writes config/era5, config/years(_edh)
    prepare_inputs.py              DEM, mask, groups.tif, group_weights.csv -> data/dem/
    prepare_terrain.py             ds_param, clusters, circular aspect, horizon -> data/terrain/outputs/
    k_design_test.py               clustering design test (k, groups, coefficients, feature weights)
    run_year.py, workflow.py       one year, month by month (QA per month, daily stats, monthly GeoTIFF)
    run_era5_queue.sh              ERA5 download lanes sharing one queue of years (lock per year)
    run_downscale_all.sh           every year with ERA5_OK -> data/runs[_v2]/YYYY (DONE / FAILED); arg v2 for v2
    check_year.py                  per-year checks: months, time axis, NaN, DJF SW sector order, SW_direct max, vs v1
    check_new_years.sh             runs check_year.py on each newly finished year -> data/logs/check_<series>/summary.log
    check_year_boundaries.py       31 Dec 23:00 -> 1 Jan 00:00 steps vs ordinary hourly steps -> check_<series>/year_boundaries.csv
    recheck_qa.py                  QA of finished months again
    update_results.py              results/ links + STATUS.md (runs every 10 min in the container)
    watch_markers.sh               host: events from DONE/RETRIED/FAILED/ERA5_OK markers
  validation/                      temperature validation against stations
    stations_prepare.py            NOAA ISD + METER.AC hourly observations, QC + despike -> data/validation/
    station_compare.py             station vs model (cluster, station elevation) -> data/validation/<series>/
    station_plots.py               hourly density, daily scatter, monthly heatmaps -> .../plots/
    era5_baseline.py               raw ERA5 and ERA5 + lapse vs TopoSCALE (RMSE, skill) -> .../plots/
    points_setup.py                station points + configs for TopoSCALE at the stations (config/points*)
    run_points.sh                  the point runs, v1 or v2
    points_validation.py           authors' obs-vs-downscaled figures, correction cross-validation -> .../points/
  maps/
    qgis_examples.py               lapse-adjusted monthly maps and v2 - v1 differences -> results/qgis_examples/
  archive/                         superseded scripts (run_era5_lane.sh)
results/                           see above (git-ignored: links + generated files)
data/  (git-ignored)
  dem/                             dem.tif, mask.tif, groups.tif, group_weights.csv
  terrain/outputs/                 ds_param.zarr, da_horizon.zarr, df_centroids.pck, terrain_summary.json
  era5_600-1000hPa/YYYY/           ERA5.zarr (input of v1 and v2), state/, logs/, ERA5_OK
  runs_v2/YYYY/, runs/YYYY/        outputs/ (downscaled/, geotiff/, months/, year_summary.json), logs/, DONE
  points/                          stations_points.csv, terrain/ (links), runs[_v2]/YYYY, logs[_v2]/
  validation/                      stations.csv, obs_hourly/; ncar/ (station_compare outputs, plots/, points/);
                                   ncar_v2/ (same, v2); edh/ (dropped series)
  logs/                            terrain, ERA5 lanes, downscale loops (downscale_all_v2_*.log), check_v2/, update_results
  era5_edh/, runs_edh/             dropped EDH series (~96 GB; delete once v2 is checked)
```

## Commands (from /app in the container)

```bash
# dataset
python rila_pirin_zarr/scripts/pipeline/make_configs.py
python rila_pirin_zarr/scripts/pipeline/prepare_inputs.py <fabdem_32634_30m.tif> <mask_30m.tif> rila_pirin_zarr/data/dem
python rila_pirin_zarr/scripts/pipeline/prepare_terrain.py rila_pirin_zarr/config/config_terrain.yml
bash rila_pirin_zarr/scripts/pipeline/run_era5_queue.sh A 2025 1940 >> rila_pirin_zarr/data/logs/era5_queue_A_<date>.log 2>&1
bash rila_pirin_zarr/scripts/pipeline/run_downscale_all.sh 2025 1940 v2 >> rila_pirin_zarr/data/logs/downscale_all_v2_<date>.log 2>&1
bash rila_pirin_zarr/scripts/pipeline/check_new_years.sh v2 1940 2025 >> rila_pirin_zarr/data/logs/check_v2/loop.log 2>&1
python rila_pirin_zarr/scripts/pipeline/check_year_boundaries.py 1940 2025 --series v2
python rila_pirin_zarr/scripts/pipeline/update_results.py --every 600 >> rila_pirin_zarr/data/logs/update_results.log 2>&1
# validation (temperature)
python rila_pirin_zarr/scripts/validation/stations_prepare.py
python rila_pirin_zarr/scripts/validation/station_compare.py --series ncar_v2
python rila_pirin_zarr/scripts/validation/station_plots.py --series ncar_v2
python rila_pirin_zarr/scripts/validation/era5_baseline.py --series ncar_v2   # run from scripts/validation/
bash rila_pirin_zarr/scripts/validation/run_points.sh v2 1959 2025
python rila_pirin_zarr/scripts/validation/points_validation.py --series ncar ncar_v2
# maps
python rila_pirin_zarr/scripts/maps/qgis_examples.py lapse 2024-01 2024-07 1942-01 1952-08
python rila_pirin_zarr/scripts/maps/qgis_examples.py diff 2024
```
Every step resumes: rerun the same command after a crash. Start long jobs detached
(`docker exec -d toposcale-rila-pirin bash -c 'cd /app && ... >> log 2>&1'`) so they do not depend on a terminal.
After killing ERA5 lanes, remove stale `data/era5_600-1000hPa/*.lock` first. What runs (no `ps` in the container):
`pgrep -af "run_year|run_downscale|check_new|update_results"` on the host.

**Redoing a month M of year Y** (LOG.md 2026-11-10): move aside `outputs/months/Y-M.json` and
`outputs/downscaled/down.zarr.progress/<M folder>`, then `run_year.py <config> --months M`, then one run without
`--months` for the year products. (v2 stores the solar geometry unpacked, so a redone month equals a fresh one.)

## Known issues (for the analysis)
- Valleys: TopoSCALE temperature comes from the pressure levels only (no surface layer, no cold pools). Below
  ~1000 m it is warm-biased (daily minimum up to +3-4 K at Sandanski) and worse than ERA5 t2m with a -6.5 K/km
  correction; on the mountains it is clearly better (validation in LOG.md 2026-11-12 and -15).
- Group boundaries: the cluster centre elevation jumps across 800 / 1500 / 2000 m (~0.4-0.6 K). The lapse-adjusted
  maps (scripts/maps/qgis_examples.py) remove it.
- TopoPyScale direct SW is 28-37 % below a clear-sky pvlib beam (A. Ionita's check): attributed to ERA5's
  direct/diffuse split, not proven.
