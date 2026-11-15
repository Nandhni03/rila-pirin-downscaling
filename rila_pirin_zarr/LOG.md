# Log: rila_pirin_zarr (clean end-to-end Rila-Pirin run)

## 2026-11-05: folder set up, clustering design decided before the run

### Why a new folder
A clean end-to-end run that uses everything learnt in `zarr_workflow/` (Rila-Pirin, k = 500, Oct 2026) and
`meridionali_zarr/` (Southern Carpathians, elevation groups, LOG_27Oct.md). `zarr_workflow/` stays as it is.

### What was copied
- `scripts/run_year.py`, `workflow.py`, `recheck_qa.py`: from `zarr_workflow/scripts/` (Docker fork, Zarr caches,
  month-by-month store, `data_repository: local`; `workflow.RANGES` already has the SW range-check fix).
- Data, logs and test outputs go to `data/` (git-ignored, `.gitignore` in this folder).

### Starting point (current production, `zarr_workflow/config/config_2025_era5_600-1000hPa.yml`)
- DEM 25 m EPSG:32634, 5079 x 4797 px, rectangle mask: 13,945,288 px, 81-2905 m.
- k = 500, no groups, features x1 y1 elevation4 slope1 aspect_cos1 aspect_sin1 svf1, minibatch k-means, seed 2.
- Area per band inside the mask: <800 m 30.3 %, 800-1000 12.9 %, 1000-1500 30.5 %, 1500-2000 16.8 %,
  2000-2500 8.5 %, >=2500 1.0 % (>= 2000 m: 832 km2; in the Meridionali domain only 1 %).

### Bug found: centroid aspect (fork)
- `aspect` is not a clustering feature, so `extract_topo_cluster_param` fills the centroid's aspect with the
  ARITHMETIC mean of the members' aspect (`df_param.groupby('cluster_labels').mean()`). Aspect is circular
  (0..2pi): a north-facing cluster with pixels at 10 deg and 350 deg gets 180 deg = south.
- `topo_scale_zarr.py:242` uses `row.aspect` for the illumination angle (direct SW on the slope).
- Current Rila-Pirin run (500 clusters): 47 centroids have aspect > 90 deg away from the circular mean
  atan2(aspect_sin, aspect_cos); 46 of the 121 north-facing clusters. Their direct SW is computed for the
  wrong slope orientation. (Possible link with the known SW sunset spikes, not checked.)
- Fix planned for this run (no change in the fork): after `extract_topo_param`, set
  `df_centroids.aspect = atan2(aspect_sin, aspect_cos) mod 2pi` before the horizon/downscaling.

### Design test `scripts/k_design_test.py` (clustering only, nothing downscaled)
- Reproduces the fork's per-group clustering on a 6 M px sample (43 % of the mask), k scaled; terrain read
  read-only from `zarr_workflow/data/runs/2025_era5_600-1000hPa/outputs/ds_param.zarr`.
- Group weights from density coefficients c_g: weight_g = area_g x c_g / sum(area x c) (clusters per km2 in a
  group proportional to c_g), rounded to multiples of 1/1024 so that the fork's `sum == 1` check holds exactly.
- Run inside Docker:
  `docker exec -w /app toposcale-rila-pirin python rila_pirin_zarr/scripts/k_design_test.py zarr_workflow/data/runs/2025_era5_600-1000hPa/outputs/ds_param.zarr zarr_workflow/data/dem/mask.tif rila_pirin_zarr/data/k_design`
  -> `data/k_design/{results.csv, summary.json}`, log `data/logs/k_design_<time>.log`.

### Design test result (round 1: 14 scenarios, 319 s, peak 3.5 GB; round 2: 8 scenarios, 191 s; tag `_round2`)
Terrain of the OLD DEM (25 m bilinear); to be re-checked on FABDEM. Overall values (all bands), pixel minus
centre. T error ~ 6.5 K/km x elev. Dec rad = clear-sky direct-beam daily factor on the slope, RMSE in % of flat
ground, circular centroid aspect (fork's arithmetic aspect in brackets). dist = pixel to centre (ERA5 cell ~21x28 km).
jump = centre-elevation step across 800/1500/2000 m (~20 m without groups).

| scenario | k | elev RMSE m | slope deg | Dec rad % | dist km | jump 800/1500/2000 m |
|---|---|---|---|---|---|---|
| S0 today: no groups, e4 | 500 | 77.8 | 4.4 | 27.5 (51.6) | 13.4 | 29/17/21 |
| S1 no groups, e4 | 1000 | 66.9 | 3.9 | 23.3 (43.9) | 11.4 | 24/17/27 |
| G1 groups c=1/1/1/1, e4 | 1000 | 29.4 | 4.6 | 33.0 | 14.1 | 89/81/97 |
| G2 groups c=0.5/1/1.5/2 (ramp), e4 | 1000 | 30.3 | 4.6 | 32.5 (55.4) | 14.4 | 97/80/90 |
| G3 groups c=0.5/1/2/4 (steep), e4 | 1000 | 31.0 | 4.8 | 32.5 | 14.9 | 104/83/81 |
| G2 ramp, e4 | 500 | 35.2 | 5.1 | 39.1 | 17.1 | 111/92/98 |
| G2 ramp, e4 | 1500 | 27.6 | 4.3 | 29.2 | 13.2 | 86/72/80 |
| G5 ramp + group >=2500 m | 1000 | 29.7 | 4.7 | 33.4 | 14.5 | (2500: 65) |
| ramp, elevation 2 | 1000 | 51.2 | 4.2 | 27.5 | 12.4 | 161/134/145 |
| ramp, elevation 8 | 1000 | 17.5 | 5.1 | 40.4 | 16.8 | 58/45/50 |
| ramp, x/y 0.5 | 1000 | 24.1 | 3.9 | 25.8 | **28.0** | 77/65/70 |
| ramp, aspect 2 | 1000 | 36.4 | 5.3 | 21.4 (41.0) | 19.3 | 111/91/102 |
| ramp, elevation 2 + aspect 2 | 1000 | 61.7 | 4.8 | 19.0 | 15.3 | 188/152/169 |
| ramp, svf 2 | 1000 | 32.7 | 4.6 | 37.4 | 16.0 | 106/85/95 |
| ramp, **elevation 6 + aspect 2** | 1000 | 26.9 | 5.6 | 22.8 (42.6) | 21.5 | 87/65/76 |
| ramp, aspect 2 + slope 2 | 1000 | 39.8 | 3.4 | 19.8 | 22.4 | 124/105/109 |
| steep, aspect 2 | 1000 | 37.8 | 5.3 | 21.7 | 20.4 | 122/91/101 |
| ramp, aspect 2 | 1500 | 33.4 | 5.0 | 19.9 | 16.2 | 107/85/93 |
| ramp, elevation 6 + aspect 2 | 1500 | 24.4 | 5.3 | 21.3 | 18.9 | 80/63/66 |
| no groups, aspect 2 | 1000 | 80.3 | 4.4 | 16.8 | 13.6 | 25/17/20 |

Findings:
- Groups are the big gain for temperature: elevation RMSE 67-78 m -> 25-35 m (~0.45 K -> ~0.2 K), also in the
  lowlands (per-group scaling makes elevation count more inside each group).
- Price of groups with today's weights: direct-SW error up (23-27 % -> 32 %), aspect/slope fit worse, and a
  centre-elevation step of ~80-100 m (~0.5-0.6 K) at each group boundary (Meridionali: 40-60 m).
- Feature weights are a dial between temperature (elevation) and radiation (slope/aspect). Aspect 2 recovers the
  SW accuracy; elevation 6 with aspect 2 keeps the temperature gain too and makes the boundary steps smaller.
- x/y 0.5 looks good on terrain but doubles the pixel-centre distance to 28 km (more than an ERA5 cell): the
  pixel would get ERA5 interpolated at a place ~1 cell away. Not recommended. svf 2 and elevation 8: SW much worse.
- Coefficients: steep (0.5/1/2/4) gains little in the alpine band once aspect 2 is used, and costs the lowlands;
  ramp (0.5/1/1.5/2) is balanced (km2/cluster: <800 m 17.7, 800-1500 ~9, 1500-2000 6.0, >=2000 4.5).
- k 1000 -> 1500: 2-3 m elevation, 1.5 % SW. Diminishing returns.
- The centroid-aspect bug nearly doubles the SW error in every scenario (e.g. 22.8 % -> 42.6 %): fix it.

## User (mid-session): new run on FABDEM, Zarr products only (no GeoTIFFs; analysis to be improved first)
- FABDEM prepared by the user today in `~/fabdem/`: `fabdem_32634_25m.tif` (same grid as the old DEM, bounds
  rounded to mm, no nodata, 53-2919 m), `fabdem_32634_30m.tif` + `mask_30m.tif` (4233 x 3998, 9,686,304 px in mask,
  same band shares as 25 m).
- The fork compares DEM/mask/groups bounds with `==`: the old `mask.tif` (649842.7286942997) would be rejected by
  the FABDEM 25 m grid (649842.729) -> mask and groups rasters must be written on the FABDEM grid itself.

## User decisions (2026-11-05, ~15:30)
- DEM: **FABDEM 30 m** (`fabdem_32634_30m.tif` + `mask_30m.tif`).
- Years: **1985-2025**, ERA5 on all levels the domain needs (14 levels 600-1000 hPa: 600 hPa ~4.2 km is above
  Musala at all times; decision of 2026-10-27) from **NCAR** (d633000 THREDDS serves 1985: checked, HTTP 200);
  EDH only as fallback (5 levels).
- Clustering: **k = 1000, groups <800/800-1500/1500-2000/>=2000 m, coefficients 0.5/1/1.5/2, features
  x1 y1 elevation6 slope1 aspect_cos2 aspect_sin2 svf1**, minibatch k-means, seed 2.
- Centroid aspect fix in our runner (fork unchanged).
- Products: Zarr (hourly `down.zarr`, daily `daily.zarr`); no daily GeoTIFFs. For visual checks one GeoTIFF per
  year: `t_mean_monthly_YYYY.tif`, 12 bands = monthly mean of the daily mean temperature.
- "Run until we get the expected results": run unattended to the end.

## Setup (2026-11-05 15:40-15:45)
- `scripts/prepare_inputs.py` -> `data/dem/`: dem.tif + mask.tif (copies of ~/fabdem, which is not mounted in the
  container), groups.tif (1 <800, 2 800-1500, 3 1500-2000, 4 >=2000 m, on the DEM grid), group_weights.csv:

  | group | band | px in mask | share | coef | weight | clusters (k=1000) |
  |---|---|---|---|---|---|---|
  | 1 | <800 | 2,947,737 | 30.4 % | 0.5 | 0.148438 | 149 |
  | 2 | 800-1500 | 4,236,241 | 43.7 % | 1 | 0.426758 | 427 |
  | 3 | 1500-2000 | 1,586,604 | 16.4 % | 1.5 | 0.240234 | 241 |
  | 4 | >=2000 | 915,722 | 9.5 % | 2 | 0.184570 | 185 |
  (fork rounds up: 1002 clusters; weights are multiples of 1/1024, `sum == 1` checked with pandas)
- `scripts/make_configs.py` -> `config/config_terrain.yml`, `config/years/config_YYYY.yml`,
  `config/era5/config_era5_YYYY.yml` (1985-2025).
- `scripts/prepare_terrain.py`: terrain once in `data/terrain/outputs/` (dem_param; [design re-check on FABDEM];
  clustering; centroid aspect fix, fork value kept as `aspect_arith`; horizon) -> `terrain_summary.json`.
- `scripts/run_year.py` (from zarr_workflow) changed: ds_param.zarr/da_horizon.zarr symlinked from data/terrain,
  df_centroids.pck copied; `compute_dem_param` NOT called (the fork rewrites a cached Zarr ds_param via
  temp+rename, which would replace the shared link); stops if the centroids lack the aspect fix; daily GeoTIFFs
  only with `--daily-geotiff`; yearly monthly-mean GeoTIFF + check (`workflow.export_year_monthly`).
- `scripts/run_era5_lane.sh`: per year import from an older store (zarr_workflow 2020 complete, 2025 Jan-Feb),
  download (2 passes), status, verify -> `ERA5_OK`. Two lanes, 12 NCAR workers each.
- `scripts/run_downscale_all.sh 1985 2025`: waits for terrain + each ERA5_OK, runs years one at a time, `DONE`/`FAILED`.

## Started (13:42-13:44 UTC)
- Terrain: `prepare_terrain.py config/config_terrain.yml --stop-after dem_param` -> `data/logs/terrain_dem_param_20261105_1542.log`
- ERA5 lane A: `run_era5_lane.sh 2020 2025 1985..2004` -> `data/logs/era5_laneA_20261105.log`
- ERA5 lane B: `run_era5_lane.sh 2005..2019 2021..2024` -> `data/logs/era5_laneB_20261105.log`

## 14:13 UTC: FABDEM terrain parameters done (1820 s), design re-checked on FABDEM
- `ds_param.zarr` 97 MB (4233 x 3998 px). Design test on it (`results_fabdem.csv`, 142 s; 9,686,304 px in mask,
  6 M sample = 62 %; note the km2 columns of the script assume 25 m pixels, x 1.44 for 30 m):

  | scenario | elev RMSE m <800/800-1000/1000-1500/1500-2000/2000-2500/>=2500 | Dec rad % circ (fork) |
  |---|---|---|
  | S0 k500 no groups e4 (old setup) | 69.4 / 70.8 / 71.3 / 75.1 / 81.2 / 117.2 | 26.3 (52.0) |
  | G2 k1000 groups e4 | 28.9 / 28.2 / 28.5 / 22.0 / 28.7 / 34.0 | 31.4 (57.1) |
  | groups e4 aspect2 | 37.0 / 35.4 / 34.3 / 25.7 / 34.4 / 41.7 | 21.4 (42.5) |
  | **groups e6 aspect2 (chosen)** | 27.3 / 25.5 / 24.8 / 19.0 / 25.0 / 29.2 | 22.9 (44.1) |
  | groups e6 aspect2 k1500 | 24.4 / 23.2 / 22.9 / 17.4 / 22.9 / 28.0 | 21.2 (41.3) |
- Same ranking as on the old DEM: the chosen setup stands. Clustering + aspect fix + horizon started:
  `prepare_terrain.py config/config_terrain.yml` -> `data/logs/terrain_cluster_horizon_<time>.log`.
- ERA5: 2020 imported from zarr_workflow (lane A now on 2025); lane B on 2005 (February after 30 min).

## 14:32 UTC: terrain complete (`data/terrain/outputs/terrain_summary.json`)
- Clustering 66 s: **1002 clusters, 149 / 427 / 241 / 185** in groups 1-4; 0 clusters spanning two groups; centre
  elevations per group 120-772, 822-1478, 1517-1982, 2026-2833 m (all inside their band).
- Centroid aspect fix: 112 of 1002 centroids moved > 45 deg, **72 > 90 deg** (fork value kept as `aspect_arith`).
- Horizon (36 azimuths) 912 s. Total 985 s.
- (The second call re-saved the cached ds_param in 7 s before clustering, then the fork added the cluster map:
  only in data/terrain, before any year links it.)
- `run_downscale_all.sh 1985 2025` started 14:31 -> `data/logs/downscale_all_20261105.log`; 2020 first (ERA5_OK).

## 2020 run (first year, test of the new runner)
- Terrain linked, centroids loaded (0 s), solar geometry 52 s, horizon sampled 3 s, ERA5 store check 0.3 s.
- 2020-01: 1002 points downscaled in 40 s (0 failed), hourly QA OK (t -16.9..13.6 degC), month 45 s in total.
- SW above 1400 W/m2 in January: 20 values (max 1887), all **west-facing clusters (aspect 270-340 deg) at 15 UTC on
  7-10 Jan** = the known TopoSCALE sunset spike (direct beam from a tiny cos(zenith), projected on a slope facing
  the low sun); also in zarr_workflow's 2020 run. Unrelated to the aspect fix (aspect = aspect_arith for 19 of 20).
  Reported by QA, not a failure. **Known issue for the analysis**: cap or recompute SW at low sun elevation.
- **2020 complete 14:46 UTC: YEAR COMPLETE, ALL CHECKS PASSED**, 768 s (12 months x ~40-50 s downscaling).
  down.zarr 805 MB, daily.zarr 49 MB; `t_mean_monthly_2020.tif` 162 MB, 12 bands, check OK (1000 pixels x 12 bands
  vs daily.zarr: max diff 1e-6 degC; nodata exactly outside the mask), range -5.9..26.6 degC.
- ERA5 speed (first hour): ~450 units/h per lane (2,274 units per year -> ~5 h/year/lane), ~5 % first attempts
  failed (timeouts, URLError, a few HTTP/OSError), all retried. Remaining 39 years on 2 lanes: ~4 days.
  Kept at 2 lanes x 12 workers (NCAR is a free service and slow today; more requests mostly add timeouts).

## 2026-11-05 evening - 11-06 00:10 UTC
- **2025: ERA5 verified 17:59 (Jan-Feb imported, rest NCAR, 4.2 h), downscaled 18:01-18:14: DONE** (all checks).
- 1985 (lane A, from 17:59) and 2005 (lane B): pressure levels fine (NCSS, 430-530 units/h), but **NCAR OPeNDAP
  (single levels) overloaded since ~19 UTC**: "NetCDF: DAP server error", HTTP 504, answers after 13-49 s.
  2005: 2265 of 2274 units after 10 h; `ncar_surf_2005-11_tp` gave up after 6 attempts (retried by the lane's
  second pass). 1985: 2244 written, single-level units of Aug-Dec still pending/retrying.
- **Change: single levels (SURF) from the CDS for every year not started yet** (1986-2004, 2006-2019, 2021-2024):
  `source.surf: cds` (one request per year, ~51 min of CDS run time; the downloader's original design; same ERA5
  values: CDS vs NCAR/EDH differences = one float32 rounding step, zarr_workflow/era5_download/LOG.md).
  Pressure levels stay on NCAR NCSS. 1985/2005/2020/2025 keep NCAR SURF (`NCAR_SURF` in make_configs.py).
  CDS credentials checked from the container (jobs endpoint 200, queue empty). The lanes read each year's config
  when they reach it, so no restart was needed.
- Watchdog now only on year-level failures (lane "NOT complete/verified", downscaling "FAILED"/"will retry").

## 2026-11-06 07:40 UTC: status
- DONE (all checks): **2020, 2025, 2005** (2005 ERA5 verified 01:46, downscaled 01:50-02:03).
- CDS SURF works: 2006 whole-year single levels in one request, 65 min (queue 33 s), written + verified.
- NCAR NCSS (pressure levels) also struggling overnight: 2006 has 1506/2274 units after 6 h, 398 failed attempts,
  12 units gave up (retried by the second pass); hourly throughput 28-428 units.
- 1985: 2269/2274 after 13.7 h; the last NCAR SURF units fail repeatedly (OPeNDAP I/O failure, ~1 unit per 10 min).
  -> **1985 SURF moved to the CDS too** (`NCAR_SURF = {2005, 2020, 2025}`): the lane's second pass requests the
  whole 1985 single-level year from the CDS (overwrites the NCAR SURF values already written: same data).

## 2026-11-06 ~08:00 UTC: FABDEM parameter QA; EDH series added (user: EDH as fallback, faster; whole 1985-2025)
### FABDEM terrain QA (`data/terrain/outputs/`, inside the mask, 9,686,304 px)
- elevation 78-2917 m (median 1114), slope 0-65.5 deg (mean 16.6, p99 38.9), aspect 0-2pi, svf 0.47-1.00
  (mean 0.941): **no NaN** in any parameter. Old DEM: slope mean 14.8, svf 0.953, max 2905 m (FABDEM is steeper
  and keeps the summits, as expected for bare-earth GLO-30). Curvature noise (median |Laplacian|) 2.80 vs 2.79 m.
- Horizon (36 azimuths x full grid): 0-73.5 deg, no NaN. Centroids: 1002, no NaN column, elevation 120-2833 m,
  svf 0.75-1.00. Every masked pixel has a cluster, no pixel outside the mask has one.
### EDH series (separate product, `config/years_edh/`, `data/runs_edh/YYYY`, `data/era5_edh/YYYY`)
- Why separate, not mixed into the NCAR years: EDH's levels within the terrain are 600/700/850/925/1000 only;
  measured vs all levels (zarr_workflow/era5_download/REPORT.md 2.6): alpine (2000-3000 m) **~0.5 K colder** in
  January, 1500-2000 m ~0.27 K. Mixing sources between years would put artificial steps into the 1985-2025 series.
- EDH store (era5-pressure-levels-v0.zarr), checked now: **19 levels** 1000/925/850/700/600/500/400/300/250/200/
  150/100/70/50/30/20/10/5/1 hPa, 1940-01-01 .. 2026-10-15. **User: take all levels EDH has** -> `plevels` = all 19.
  `topo_scale_zarr` interpolates only between the level just above and just below each centroid
  (topo_scale_zarr.py:160-177); every level above 600 hPa lies above 2918 m, so the extra levels cost download
  only and do not change any value.
- `run_downscale_all.sh` got an `edh` variant (run_year.py fetches EDH itself via mp.get_era5, no ERA5_OK). The
  running NCAR loop was idle and was restarted from the edited script (bash reads scripts while running).
- Started: `run_downscale_all.sh 1985 2025 edh` -> `data/logs/downscale_all_edh_20261106.log`; NCAR loop restarted
  (same log as before). NCAR lanes keep running: the 14-level series is completed in parallel.
- **User correction (~08:15): only the EDH levels that are useful for us** -> EDH configs back to the 600-1000 hPa
  request; the fork resolves it to **600/700/850/925/1000 hPa** (checked with `resolve_plevels`; 600 hPa ~4.2 km is
  above the highest centroid, 2833 m, so nothing is extrapolated). Applies from 1986 (the loop reads each year's
  config when it starts the year).
- EDH 1985 was already fetched with all 19 levels (420 s, store 9720 h: the fork fetches whole EDH time chunks;
  the downscaler selects the year). Kept: only the two levels around each centroid enter the calculation, all
  within 600-1000 hPa, so its values are the same as with 5 levels. Its ERA5 store just holds 14 unused levels.

## 2026-11-06 08:05 UTC: session restarted (previous Claude session closed), both series still running
- Nothing was lost: loops and ERA5 lanes run inside the container. State at 08:05: NCAR series DONE 2005/2020/2025;
  1985 second pass (CDS single levels) since 07:53; 2006 plev 1683 parts written. EDH series: 1985 at month 6, ~110 s/month.
- **Results organised in `results/`** (user request): `scripts/update_results.py` links every finished year
  (`results/ncar_14levels/YYYY`, `results/edh_5levels/YYYY`, plus all monthly GeoTIFFs per series in
  `t_mean_monthly/`) and writes `results/STATUS.md` (all years x both series). Runs detached in the container every
  10 min (`docker exec -d`, log `data/logs/update_results.log`), so it survives a closed session.
- Watchers re-armed (finished/failed years in both series; watchdog on year-level failures).
- 08:40: the loop/lane stdout logs (`data/logs/downscale_all_*.log`, `era5_lane*_20261105.log`) stopped at the
  session close (their `docker exec` clients were in the closed session; the processes live on, stdout goes nowhere).
  Not restarted (would kill 1985's running CDS request). Per-year logs and markers are unaffected. Watching now via
  `scripts/watch_markers.sh` (DONE/RETRIED/FAILED/ERA5_OK + a lane that moved on from an unverified year);
  `update_results.py` detects "downscaling" from the run folder.
- **EDH speed with 5 levels: 1986 in 18 min** (08:19-08:37, download + 12 months). 1985 (19 levels) 33 min.
  -> remaining 39 EDH years ~12 h, **EDH series complete ~20:30 UTC today**.
- **NCAR 1985 DONE 09:2x** (ERA5 verified after the CDS single-level pass). First year done in both series.
- **EDH vs NCAR, 1985, daily t_mean per cluster (EDH minus NCAR), by centroid elevation band:**
  | band | n | year | Jan | Jul | days with abs diff > 1 K |
  |---|---:|---:|---:|---:|---:|
  | <800 m | 149 | -0.15 K | -0.26 | -0.10 | 5.4 % |
  | 800-1500 | 427 | -0.01 | -0.00 | -0.04 | 0.0 % |
  | 1500-2000 | 241 | +0.04 | -0.22 | +0.07 | 1.9 % |
  | >=2000 | 185 | +0.16 | -0.34 | +0.31 | 8.6 % |
  Seasonal, opposite in winter/summer in the alpine zone (EDH colder in Jan, warmer in Jul): consistent with the
  January finding (REPORT.md 2.6). Annual means differ little, but seasonal/daily values do -> keep the series apart.
- 09:50: watchdog: **NCAR 2006 not verified** (lane B moved on to 2007). One unit missing: `ncar_plev_2006-05-29_z`, a
  corrupt raw NetCDF that the second pass reused. Moved to `2006/raw_bad/`, re-downloaded (1.6 min), verify OK,
  ERA5_OK written by hand at 09:53 (same as the lane does). Downloader fixed so bad raw files are set aside
  (zarr_workflow/era5_download/LOG.md); applies to every year a lane starts from now on.

## 2026-11-06 17:00 UTC: status, third ERA5 lane prepared (user: yes, after EDH)
- NCAR 7/41 done (1985, 1986, 2005, 2006, 2007, 2020, 2025), EDH 29/41 (1985-2013; ETA ~20:30 UTC).
- NCAR NCSS slower this afternoon: 150-210 parts/h per lane (was 330-400), ~1 failed attempt per 2 written; all retried.
- Memory peak ~15:50 (59/62 GB) when an NCAR and an EDH year downscaled at the same time (~20 workers x 1.3 GB each);
  back to 19 GB used at 17:00. Disappears when the EDH series is finished.
- `scripts/run_era5_queue.sh`: lanes share one queue with an atomic per-year lock (`YYYY.lock`), logs written inside
  the container; needed for a 3rd lane (the fixed lists of run_era5_lane.sh would make two lanes write the same year).
  Switching lanes A/B to it means stopping them (downloads resume); **waiting for the user's OK** (blocked by the
  permission check as interfering with running work).
- `watch_markers.sh`: lane-order check replaced by the ERA5_FAILED marker of the queue script.
- **17:04: user OK ("go ahead") -> lanes switched to the queue.** Old lane scripts (pids 761, 767) and their
  downloaders (1987, 2008) stopped; the downloaders died on SIGTERM (left as zombies, state Z, no writes) before the
  queue lanes started. Queue lanes A and B (`docker exec -d`, logs `data/logs/era5_queue_{A,B}_20261106.log`)
  resumed 1987 (372/2191 units already written) and 2008 (84/2197). Locks `1987.lock`, `2008.lock` show the owners.
  An interrupted unit is redone (not in the manifest), and verify checks every month for missing hours/NaN.
- **Lane C scheduled** inside the container: waits until all 41 EDH years are DONE/FAILED, then runs
  `run_era5_queue.sh C 1985 2025` (log `data/logs/era5_queue_C_20261106.log`). To check after ~2 h of C: total
  parts/h of all lanes vs ~360-420/h with 2 lanes; if NCAR only times out more, stop C (and remove its .lock).

## Decisions of 2026-11-06 (summary; details in the entries above)
| # | decision | why |
|---|---|---|
| 1 | Single-level ERA5 variables from the CDS (one request/year) for all years except 2005/2020/2025 | NCAR OPeNDAP overloaded since 11-05 19 UTC; CDS = same values (one float32 rounding step); 5-7 min/year |
| 2 | EDH as a second, complete 1985-2025 series (`runs_edh/`), not mixed into the NCAR series | user: EDH as fast fallback; EDH has only 600/700/850/925/1000 hPa -> seasonal offsets in the alpine zone |
| 3 | EDH with only the useful levels 600/700/850/925/1000 (1985 has all 19, same values) | user correction; 600 hPa (~4.2 km) is above the highest centroid (2833 m) |
| 4 | NCAR series = final dataset | 1985 comparison: EDH minus NCAR at >=2000 m Jan -0.34 K, Jul +0.31 K, 8.6 % of days > 1 K |
| 5 | `results/` with links per series + auto STATUS.md (every 10 min, in the container) | user: results organised and easy to find |
| 6 | Watch marker files, not loop stdout | loop/lane stdout died with the closed session |
| 7 | Corrupt raw downloads moved to `raw_bad/` and re-downloaded | 2006-05-29 z: corrupt file was reused by every retry |
| 8 | ERA5 lanes on one shared queue with per-year locks; 3rd lane after EDH | user: yes to a 3rd lane; fixed lists would let two lanes write the same year; memory free only after EDH |

## 2026-11-07 10:45 UTC: status; lane C kept
- **EDH series complete: 41/41** (last year ~20:25 UTC 11-06), no FAILED/RETRIED.
- NCAR series **13/41** done (1985-1991, 2005-2008, 2020, 2025); no ERA5_FAILED, no RETRIED/FAILED.
- Lane C started 20:25 UTC when EDH finished. Time per year per lane with 3 lanes: A 1989 5.9 h, B 1990 6.3 h,
  C 1988 6.2 h / 1991 6.1 h, i.e. the same as with 2 lanes -> a third lane adds ~50 % throughput (~1,080 parts/h
  in total vs ~720). **Decision: keep C.**
- In progress: 1992 (A, 1835/2191), 1993 (B, 1621), 1994 (C, 749). 25 more years queued -> ~8-9 years per lane x
  ~6.1 h -> **NCAR series complete ~Mon 2026-11-09 afternoon UTC** if NCAR holds this speed.
- Memory: 11 GB used (only one series downscaling now).

## 2026-11-09 16:34 UTC: both series complete
- **NCAR series (final dataset): 41/41** (last: 2024 at 16:34 UTC). **EDH series: 41/41** (since 11-06 ~20:25 UTC).
  No RETRIED / FAILED / ERA5_FAILED in either series; every NCAR year has ERA5_OK (verify: no missing hours/NaN).
- Corrupt raw NCAR downloads caught by the `raw_bad/` fix (11-06) and re-downloaded automatically: 15 files in
  14 years (1992, 1993, 1994, 1997 x2, 2000, 2002, 2004, 2006, 2008, 2011, 2012, 2015, 2016, 2023); at most two per
  year, all on different days/variables -> isolated transfer errors, not a systematic problem.
- NCAR throughput with 3 queue lanes stayed ~6 h per year per lane until the end (2013-2024 in ~44 h).
- Yearly monthly-mean temperature range (QA, 30 m GeoTIFF): min -13.5 (2003) .. -5.2 degC (2014), max 24.4 (1991)
  .. 29.9 degC (2024); NCAR vs EDH ranges agree within 0.3 K for every year.
- Disk: `data/runs` 42 GB, `data/runs_edh` 42 GB, `data/era5_600-1000hPa` 7.3 GB.
- Queue lanes A/B/C ended by themselves (queue empty). Still running: `update_results.py --every 600` (harmless;
  stop it or leave it, results/ is final). Host watchdog stopped.

## 2026-11-10 12:15-12:35 UTC: extension back to 1940 (user: "downscale also from 1985 until 1940")
User request read as 1940-1984 ("1085" = 1985; ERA5 starts 1940-01-01). Same terrain, clusters, levels and
products as 1985-2025; both series (NCAR 14 levels = final, EDH 5 levels = fast). Every move, in order:
- **Container was stopped** (host restart since 11-09; this also ended the `update_results.py` refresher).
  `docker compose up -d`: data intact, no stale `*.lock`, CDS credentials present (`/home/icam/.cdsapirc`).
- **Data availability checked before configuring** (12:28): NCAR d633000 THREDDS catalog starts at `194001`;
  NCSS subset of `t` for 1940-01-01, 1958-06-01, 1978-12-31, 1979-01-01: HTTP 200 each (the 1940-1978 back
  extension is served with the same file names). CDS ERA5 single levels and EDH (LOG 11-06: 1940-01-01 ..) start 1940.
- Disk 682 GB free (needs ~2 x 45 GB runs + ~8 GB ERA5); memory 53 GB available.
- `make_configs.py --years 1940 1984`: 135 new configs (era5/, years/, years_edh/). `config_terrain.yml` rewritten
  byte-identical (git: no change). Single levels from the CDS for all 45 years (none is in `NCAR_SURF`).
- **Script changes (minimal):**
  - `run_era5_queue.sh`, `run_downscale_all.sh`: `Y0 > Y1` counts down (`seq Y0 -1 Y1`; plain `seq 1984 1940` is
    empty, so a lane would have ended at once with "queue empty"). Ascending calls behave as before.
  - `update_results.py`: `YEARS = range(1940, 2026)`, title 1940-2025 (otherwise the new years never reach results/).
- **Order decisions:**
  - NCAR (final dataset) **newest first, 1984 -> 1940**: if the run is stopped early, the final series is still
    continuous back from 2025.
  - EDH **oldest first, 1940 -> 1984**: EDH takes ~20 min/year, so 1940 (earliest ERA5 year, pre-1970 = negative
    Unix times, sparse-observation back extension) tests the whole chain within the first hour, hours before the
    first NCAR year has its ERA5 (~6 h/year/lane).
  - Lanes as in the 1985-2025 run: NCAR queue lanes A + B now, **lane C only after the EDH loop ends** (11-06: an
    NCAR and an EDH year downscaling together peaked at 59/62 GB; a 3rd lane = +50 % NCAR throughput).
- **Started 12:29-12:31 UTC** (all `docker exec -d`, logs in `data/logs/`, `*_20261110.log`):
  `run_downscale_all.sh 1940 1984 edh`; `run_era5_queue.sh A 1984 1940` (took 1984), `B` (took 1983);
  `run_downscale_all.sh 1984 1940`; waiter that starts `run_era5_queue.sh C 1984 1940` when the EDH log says
  "all years done"; `update_results.py --every 600`.
- Expected: EDH 45 years ~15 h (~Wed 11-11 04 UTC); NCAR ~45 years / 2-3 lanes x ~6 h -> ~4 days (~Sat 11-14).

## 2026-11-10 12:45-13:10 UTC: EDH 1940-01 failed QA -> ERA5 start gap found and filled
- **Symptom** (EDH 1940, first year of the test): `1940-01: failed checks`; `months/1940-01.json`: **LW 6773 values
  < 50 W/m2, min -4.4** (all other variables in bounds; SW 16 = known sunset spike). Feb-Jun 1940: QA OK.
- **Diagnosis:** the EDH input `data/era5_edh/1940/ERA5.zarr` has NaN in **ssrd, strd, tp only, at 1940-01-01 00..06
  UTC (7 h x 110 cells = 770 values)**; nothing else in 1940 is missing. Cause: ERA5 starts 1940-01-01 00 UTC but
  accumulated fields come from forecasts started 06/18 UTC, the first at 1940-01-01 06 UTC, so those 7 hours of
  accumulations do not exist in ERA5. The fork turns the NaN into ~0: downscaled LW 17-19 W/m2 (should be ~200),
  tp = 0 silently (passes QA), SW 0 (correct anyway, night). 6773 = the 7 h x 1002 clusters minus a few.
- **Same problem waits in the NCAR series:** `convert_cds_surf` keeps t2m at every hour, so the 7 accumulation hours
  would be NaN -> `check_unit` "NaN values" -> raw file to raw_bad/ -> the ~50 min whole-year CDS request repeated,
  failing in both passes -> 1940 `ERA5_FAILED`.
- **Decision: fill exactly those 7 hours in the ERA5 input** (not drop the hours: every year keeps 8760/8784 h;
  not leave ~0 LW / invented tp). Values, chosen from the data:
  - ssrd = 0: before sunrise; other years' 06 UTC value on 1 Jan is <= 1 W/m2 (1985/1990/2000/2020 max 0.5-0.96).
  - tp = 0: 1940-01-01 07-12 UTC is dry everywhere (max 0.012 mm in one cell).
  - strd = eps * sigma * t2m^4, eps per cell from 07 UTC (first valid hour; t2m exists at all hours) -> 196-199 W/m2
    area mean (155-257 per cell), continuous with 07 UTC (200.5).
- **Code (one function, two callers; fork untouched, raw data untouched):**
  - `zarr_workflow/era5_download/era5_download.py`: `fill_era5_start_gap(ds)`; called in `convert_cds_surf` (NCAR
    series, CDS single levels) and logged per unit. No-op unless those variables are NaN, **raises if NaN occurs
    outside 1940-01-01 00-06 UTC** (a real data problem is never filled silently).
  - `rila_pirin_zarr/scripts/run_year.py`: `fill_edh_start_gap(store)` after `get_era5` (EDH series): region write of
    the first hours in place. Needed there because the fork's `assemble_zarr` rebuilds ERA5.zarr from the cached
    edh_blocks on every run, so a one-off patch of the store would be lost on the retry.
  - Backups: scratchpad `era5_download.py.bak_20261110`, `run_year.py.bak_20261110`.
  - Safe for running jobs: every year starts a new python process (running ones keep their loaded code); the bash
    loop/lane scripts were not edited (bash reads a running script from disk).
- **Tests:** in memory on EDH 1940: 7 h x 3 variables filled, everything else bit-identical, float32 kept, idempotent,
  1985 = no-op, a NaN outside the gap raises. In place on a copy of the 1940 store: only the 770 x 3 values changed,
  time axis identical. CDS: real January 1940 request via the downloader (test config `data/tmp_cdstest/`): see below.
- **Rerun of EDH 1940-01:** run_year redoes only months whose status is not "ok". The EDH loop marks 1940 RETRIED
  (exit 1 because of January) and retries it after 1984; the retry rebuilds the store, fills the gap, redoes January.

## 2026-11-10 12:47-13:16 UTC: EDH 1940-01 redone; second finding (packed solar geometry); EDH 1940 DONE
- **Rerun 1 (`--months 1`) did not recompute anything:** "0 points to downscale (1002 already done)". The fork's
  resume marks every point of a month as done (`down.zarr.progress/<month>/<i>.done`) when it is written, whether or
  not the month later passes QA. -> January's markers moved to `runs_edh/1940/progress_bad/` (kept), rerun:
  1002 points, QA OK, LW 1 Jan 00-06 UTC now 199-201 W/m2 (was 17-19), January LW min 119.8 W/m2.
- **But SW had changed too** (16 -> 14 sunset spikes, SW at 08 UTC 168.49 -> 168.3), on every point and every
  daylight hour of January, max 971 W/m2. Not accepted unexplained. Steps:
  1. Same input twice -> bit-identical: the downscaling is deterministic.
  2. Isolated run (copy of the EDH blocks, **pre-fix run_year.py**, gap NaN) -> reproduces run 1 exactly (16 spikes).
  3. Fork `downscale_point` called directly for point 0, NaN vs filled input, same solar geometry -> **only LW
     differs, only the 7 gap hours; SW bit-identical**. So the gap fill changes exactly what it should.
  4. Cause of the SW change: **`ds_solar.zarr` is stored packed as int16 + scale_factor by the fork** (mu0 step
     0.0009, SWtoa 1.27 W/m2, zenith 0.14 deg). A run that computes the solar geometry downscales with the exact
     float64 values in memory; a rerun reads the packed store. Tiny everywhere, large only at tiny mu0 (sunset spikes).
  5. Every 1985-2025 year (both series) has exactly one run_year log -> all downscaled with fresh float64 solar
     geometry: the dataset is consistent. Only a resumed/redone month would use the packed values.
- **Decision: January redone with fresh solar geometry** (ds_solar.zarr removed, month json + progress moved aside,
  all three checked absent before the run). Result vs the isolated pre-fix fresh run: **SW, SW_direct, SW_diffuse,
  t, tp bit-identical; LW differs only at 1940-01-01 00-06 UTC**. 16 SW spikes (same as fresh runs elsewhere).
  (Two attempts were wasted on the way: one skipped the month because its json said ok, one still had the progress
  markers. Rule now written down below.)
- `--months` runs do not write the year products: one plain run_year call (all 12 months "complete, skipped") wrote
  `year_summary.json` and **`t_mean_monthly_1940.tif`: check OK, range -11.8..25.1 degC**. `DONE` written by hand
  (13:13, like 2006 on 11-06), so the loop's retry after 1984 skips 1940.
- **Rule for redoing a month M of year Y:** move aside `outputs/months/Y-M.json`, `outputs/downscaled/down.zarr.progress/
  <M folder>`, and delete `outputs/ds_solar.zarr` (recomputed fresh, ~52 s); run `run_year.py ... --months M`; then
  one run without `--months` for the year products.
- EDH 1941 DONE 13:05 (19 min); loop on 1942. NCAR lanes: 1984 242 and 1983 231 parts by 13:15 (~320/h/lane,
  ~6.8 h/year), ~4 % first attempts time out, all retried (as last week). Memory 33/62 GB used.
- Test files removed (`data/tmp_det/`, the pre-fix script copy). CDS January 1940 test still running.

## 2026-11-10 14:44 UTC: CDS test January 1940 (NCAR series path) passed
- Downloader on a January-1940 test config, `download --only surf`: CDS request queued/run 123 min (slow CDS today;
  last week 51-65 min/yearly request; still shorter than a lane's ~6.8 h of pressure levels per year).
- The CDS GRIB has the **same gap** (ssrd/strd/tp, 1940-01-01 00-06 UTC); `convert_cds_surf` filled it
  ("ERA5 start gap ... filled, hours per variable {'ssrd': 7, 'strd': 7, 'tp': 7}") and the unit was **written and
  verified** (no NaN). Filled strd 195.62/196.05/... W/m2, 07 UTC 200.46 (EDH 200.47: one float32 step) -> both
  series get the same ERA5 input in the gap. NCAR 1940 needs nothing by hand. Test folder removed.
- EDH series: 1940-1946 DONE by 14:44 (~19 min/year), no RETRIED/FAILED since 1940.

## 2026-11-10 19:05 UTC: first NCAR years of the extension verified
- NCAR ERA5_OK: **1983 18:52, 1984 19:05** (~6.4-6.6 h per year per lane, as expected). 1984: one corrupt raw file
  (`ncar_plev_1984-10-22_t.nc`, 17:40) set aside in raw_bad/ and re-downloaded by the second pass (fix of 11-06).
  CDS single levels: one request per year, 280-287 s to write. Lanes moved on to 1982 / 1981.
- NCAR 1983 downscaling started 19:01 (loop takes verified years in its 1984->1940 order; 1984 next).
  Jan/Feb QA OK. Memory with an NCAR and an EDH year downscaling together: 26 GB used, 36 GB available.
- EDH: 1940-1961 DONE (22/45), no RETRIED/FAILED since 1940.

## 2026-11-11 ~03 UTC: EDH vs NCAR check on an extension year (1983 vs 1985)
- NCAR DONE: 1984, 1983, 1982, 1981 (series continuous 1981-2025). EDH: 1940-1983 DONE (44/45).
- Daily t_mean EDH minus NCAR per cluster, by centroid band (year / Jan / Jul / days |d| > 1 K):
  | band | 1983 | 1985 |
  |---|---|---|
  | <800 m | -0.18 / -0.23 / -0.07 / 6.8 % | -0.15 / -0.26 / -0.10 / 5.4 % |
  | 800-1500 | -0.01 / +0.00 / -0.03 / 0.0 % | -0.01 / -0.00 / -0.04 / 0.0 % |
  | 1500-2000 | +0.04 / -0.02 / +0.05 / 1.5 % | +0.04 / -0.22 / +0.07 / 1.9 % |
  | >=2000 | +0.14 / -0.04 / +0.23 / 9.1 % | +0.16 / -0.34 / +0.31 / 8.6 % |
  Same annual offsets per band; the January alpine offset depends on the winter (inversions the 5 EDH levels miss).
  -> the extension behaves like 1985-2025; the two series still must not be mixed.

## 2026-11-11 01:42 UTC: EDH series complete 1940-2025; NCAR lane C started
- **EDH 1940-1984: 45/45 DONE** (01:38:58; loop: "all years done: 86 DONE, 0 FAILED" = EDH 1940-2025 complete).
  ~17-20 min per year; the only problem was 1940-01 (start gap, fixed). No RETRIED/FAILED otherwise.
- Lane C waiter fired as planned; **lane C took 1978 at 01:41** (A 1980, B 1979). CDS single-level request accepted
  after 3 s. Memory 6 GB used now (only NCAR downscales from here on).
- NCAR: 1981-1984 DONE. Remaining 41 years (3 running + 38 queued) / 3 lanes x ~6.5 h -> ~14 rounds ->
  **NCAR series complete ~Sat 2026-11-14 evening to Sun 11-15 morning UTC** if NCAR holds this speed.

## 2026-11-11 ~12:00 UTC: NCAR 1978-1980 DONE; second aspect bug found (azimuth convention), runs NOT stopped
- NCAR 1980 (07:32), 1979 (07:45), 1978 (08:51) DONE; 12/12 months QA ok, 0 failed points; t_mean monthly
  ranges 1980 -10.7..25.2, 1979 -9.2..23.9 (EDH -9.3..23.9), 1978 -9.2..25.0 degC. NCAR now 1978-1984 done.
- Trigger: `git fetch andrei` (read-only, nothing merged): Andrei's commit 2460386 "aspect fix + some validation"
  reruns his years with a fixed TopoPyScale (his local bbd0296, branch fix/aspect-azimuth-convention; "aspect / SW /
  vertical-fallback fixes"; the code and his CHANGELOG are NOT on GitHub, only his log and check_year_fixed.py).
- **Diagnosis in our fork (same bug, NOT covered by our centroid fix of 2026-11-05):**
  - aspect: `topocalc.gradient.gradient_d8` -> degrees clockwise from NORTH; topo_param.py:250 only does deg2rad.
  - sun azimuth: solar_geom.py:81 `deg2rad(180 - pvlib_azimuth)` -> 0 = SOUTH, positive east (its docstring says so).
  - topo_scale_zarr.py:242 `cos(azimuth - aspect)` mixes the two: north and south are swapped (E/W happen to match).
  - Our centroid fix (circular mean) keeps the north convention, so it does not touch this.
- **Check on our output (read-only, NCAR 2000, 876 clusters with slope >= 10 deg, DJF means):**
  | sector | SW_direct DJF | SW DJF | SW JJA | n |
  |---|---|---|---|---|
  | N | 92.2 | 123.9 | 269.9 | 210 |
  | E | 47.0 | 78.5 | 242.5 | 226 |
  | S | 19.8 | 51.2 | 236.8 | 208 |
  | W | 64.2 | 95.7 | 267.7 | 232 |
  North slopes get ~4.7x the winter direct SW of south slopes: physically reversed at 42 N. Also SW_direct max
  1920 W/m2 (> solar constant; the known sunset spikes, Andrei: "old code had spikes up to ~2900").
- Affected: SW and SW_direct (SW_diffuse uses svf, not the illumination angle) in BOTH series, ALL years 1940-2025.
  Not affected: t, q, p, u, v, ws, wd, tp, LW (TopoSCALE computes them without the illumination angle), so the
  t_mean GeoTIFFs and every temperature result stand.
- **Decision: keep the NCAR 1940-1977 runs going.** Stopping would not save anything: a fix only needs a
  re-downscale per year from the ERA5 already on disk (~20 min/year/lane), and the download is the slow part.
  The fix itself is a fork change and must not be applied while lanes import the fork (mixed code within the series).
- Fix not applied; waiting for the user (to-do list given in the session). Script: scratchpad aspect_check.py.

## 2026-11-11 ~12:30 UTC: station validation of temperature (both series), read-only on the runs
- User: validate temperature only, both periods (recent METER.AC + long NOAA). Runs not touched (nice 19, reads DONE years).
- Stations: NOAA ISD hourly downloaded to rila-pirin-data/stations/noaa_isd_hourly (179 files, 16 MB; Musala 156150,
  Sandanski 157120, Ihtiman 156220, Berovo 135980). GHCN-Daily has no station in the domain (checked ghcnd-stations).
  Ihtiman and Berovo are inside the rectangle but outside the clustering mask -> dropped. Used: Musala, Sandanski
  + 28 METER.AC nodes (2018-2026).
- Decisions: Musala ISD coordinates (3 decimals) hit a 2713 m pixel -> took the METER.AC N306 position (same summit,
  2917 m pixel). Day valid = all 8 synoptic hours or >= 20 h; model sampled at the station's hours (1950s: almost
  no valid days, so the long record starts ~1960). Elevation adjustment with a daily local lapse rate (50 nearest
  clusters, as Andrei). ISD quality codes 2/3/6/7 dropped; METER.AC only 'complete' hours.
- New scripts: scripts/stations_prepare.py, scripts/station_compare.py -> data/validation/{stations.csv,obs_hourly,
  ncar,edh}.
- Results t_mean (station elevation), EDH 1940-2025 / NCAR 1978-2025 (NCAR still running):
  - Musala (NOAA): +0.87 / +0.77 K, RMSE 1.44 / 1.38, r 0.99. METER.AC Musala gives the same (+0.85 / +0.80):
    the two independent records agree. Without the elevation adjustment +1.43 / +1.35 (cluster centre 92 m lower).
  - Sandanski 207 m: -0.27 (EDH) vs +1.04 (NCAR); r 0.96 / 0.98. Series differ most here (valley, low levels).
  - METER.AC 375-2525 m: -2.1 .. +2.7 K; most valley/basin nodes +1 .. +2.7 K, warm in Oct-Feb (missed cold pools).
  - Everywhere t_max too low and t_min too high (Sandanski EDH t_max -3.3, t_min +2.2; Musala -0.2 / +1.9):
    diurnal range too small, as Andrei found in the Carpathians.
  - Per decade the bias is stable at Musala (0.7-1.3 K, 1960s-2020s); Sandanski t_min bias grows (+1.8 -> +2.7 K).
  - Sandanski Feb-Mar and Sep-Oct negative, Jun-Aug positive in EVERY decade -> a real model feature, not sampling.
  - Lag test: t_min fits the model's same day best at Musala (0.982 vs 0.932); at Sandanski same day and day before
    are equal (0.928 / 0.930).

## 2026-11-11 ~13:10 UTC: validation figures, steps 1 and 2 of the plan (user: "1 and 2 now, and 3 and 4 later")
- Plan (from the comparison with the authors' Finse example and Andrei's 9 Nov figures):
  1 authors' hourly view (density scatter, regression, N/r/RMSE/bias; topo_compare.obs_vs_downscaled style,
    bias sign flipped to model - station like all our tables), 2 Andrei's daily scatter grid + monthly heatmap,
  3 later: point downscaling (method: points) at the stations, 4 later: lapse-adjusted maps for chosen periods.
- station_compare.py now also writes matched_hourly.parquet (every station hour; cluster and station-elevation
  model). New scripts/station_plots.py -> data/validation/<series>/plots/: hourly_density_{recent,longterm}.png,
  daily_scatter_{recent,longterm}.png, monthly_heatmap_recent.png, monthly_heatmap_longterm_{Musala,Sandanski}.png,
  hourly_stats_{recent,longterm}.csv. recent = 2018-2025, 23 stations with >= 200 valid days.
- Seen in the hourly view (EDH): regression slopes 0.69-0.94 (model range too small), lowest at valley nodes
  (Dolno Draglishte 0.69, Riltsi/Boboshevo 0.73) with RMSE 4.7-6.0 K; ridges/high sites 0.89-0.94, RMSE 1.8-2.9 K.
  Musala long-term decade x month heatmap: +1.2..+1.9 K in Nov-Feb, +0..+0.5 K in Jul-Aug in every decade.

## 2026-11-12 ~11:30 UTC: raw ERA5 baseline for the station validation (NCAR)

**Why.** The station plots showed how good TopoSCALE is, not what it adds. A downscaling has to be compared with what
you would have without it (user's request).
**What.** New `scripts/era5_baseline.py`. It reads `data/validation/ncar/matched_hourly.parquet`, so it uses the
same station hours, valid days and statistics as TopoSCALE. It compares four versions:
- `era5_raw`: ERA5 t2m of the nearest grid cell.
- `era5_lapse`: t2m bilinear + (-6.5 K/km) × (station elevation - ERA5 orography, z_surf/g bilinear).
- `ts_cluster`: TopoSCALE, the cluster value.
- `ts_station`: TopoSCALE at station elevation.
ERA5 comes from `data/era5_600-1000hPa/<y>/ERA5.zarr` (single levels from CDS, the same ERA5 surface data the EDH
series uses). Skill = 1 - RMSE(TopoSCALE)/RMSE(ERA5).
Before it, `station_compare.py --series ncar` was rerun to cover NCAR 1966-2025.
Outputs in `data/validation/ncar/plots/era5_*`. The runs are only read.

**Decisions.**
- Two ERA5 references. Raw ERA5 is the "no downscaling" case. The lapse-corrected one is the cheap alternative a
  reviewer will ask about, so TopoSCALE is judged against both.
- Fixed -6.5 K/km, not the daily local lapse rate. That rate is fitted on TopoSCALE clusters, so it would leak
  model information into the baseline.

**Result, RMSE of daily t_mean, NCAR, same days for all versions:**

| station | period | raw | +lapse | TopoSCALE |
|---|---|---|---|---|
| Musala NOAA | 2018-2025 | 10.2 | 2.9 | 1.4 K |
| Musala NOAA | 1966-2025 | 10.2 | 3.1 | 1.4 K |
| Sandanski NOAA | 1966-2025 | 2.6 | 1.5 | 2.2 K |

- TopoSCALE clearly adds value at stations ABOVE the ERA5 orography: Musala (+1620 m), Malyovitsa (+740 m),
  Ortsevo, Obidim, Popovi livadi (+456 m, vs raw). Skill there is +0.3..+0.6 against ERA5 + lapse.
- At most valley and low stations, BELOW the ERA5 orography (Sandanski -610 m, Dolno Draglishte -640 m, Garmen,
  Riltsi, Boboshevo, Dabnitsa ...), TopoSCALE is WORSE than ERA5 + lapse (skill -0.5..-1.3). On daily t_min it is
  often worse than raw ERA5 too.
- In the monthly bias, ERA5 + lapse is +1..+2 K in winter and ~0 in summer at the valley stations. TopoSCALE is
  +2..+4 K in winter and +1..+1.5 K in summer, so warmer all year, not only in winter.

**Hypothesis, not yet checked.** Below the ERA5 surface, TopoSCALE uses pressure-level temperature that ERA5
extrapolates underground (no boundary layer, no inversion). ERA5 t2m does include the surface layer. This would
explain why the sign of the skill follows station elevation minus ERA5 orography. Andrei's unreleased
"vertical-fallback" fix may be about this case. To check: TopoPyScale's handling of points below the lowest valid
level, and skill vs dz_station_minus_era5 as one plot.

## 2026-11-12 ~11:50 UTC: units checked; station spikes removed

- **Units.** The user asked for attention to °C vs K. Checked at every step:
  - ERA5 t2m is in K (249.7..312.4) and is converted to °C (`- 273.15`).
  - down.zarr t is in K (253..282 in Jan 1980) and is converted to °C in station_compare.py.
  - Station data is in °C.
  - Temperatures are labelled [degC] and differences (bias, RMSE) [K]. A difference of 1 K equals 1 °C. No error.
- **Found while checking.** The observed minimum was -55.0 °C: ISD passed Musala -55.0 at 1995-11-20 13 UTC
  (-16.3 and -17.6 around it), and +29.0 / +29.5 °C in summer at 2925 m.
- **Fix: `despike()` in stations_prepare.py.** Applied to ISD and METER.AC.
  - Physical limits: -40..+46 °C everywhere, max +25 °C at Musala.
  - Isolated spikes: a reading that jumps away from BOTH neighbours in the same direction by > 10 K (neighbours
    <= 3 h) or > 20 K (<= 6 h). The second rule covers old 6-hourly records, where 10 K can be a real afternoon peak.
- **Rejected first version.** Dropping > 5 robust sigmas from the monthly median also removed real cold spells
  (Malyovitsa -15 °C in December, Ihtiman -27 °C in Jan 1954). Real cold pools build up over hours; spikes don't.
  Dolno Draglishte at -16 °C under +5 °C free air is kept: a real Razlog-basin cold pool.
- **Effect.** 16 of ~410k hours dropped (Musala 10, Sandanski 5, Berovo 1). Observed range is now -31.6..+42.9 °C.
  Daily statistics are unchanged at 2 decimals, since the spikes were mostly on days that are not valid anyway.
  The hourly scatter axes no longer stretch to -55.
- **Rerun.** stations_prepare, then station_compare (ncar, edh), then station_plots (ncar, edh), then
  era5_baseline (ncar).

## 2026-11-12 ~14:20 UTC: validation step 3, TopoSCALE run at the station points (NCAR 2018-2025)

**Why.** To separate the clustering error from TopoSCALE's own error (user: "3+", i.e. go on with step 3). This is
the authors' approach in their Finse example.
**Setup.** New `scripts/points_setup.py`:
- 32 points = the stations in the domain (stations.csv). Elevation = the surveyed station elevation; pixel
  elevations are within 15 m.
- Slope, aspect and svf come from the station's 30 m pixel. The horizon is sampled by compute_horizon.
  aspect_arith = aspect.
- Outputs go to `data/points/` (terrain links, df_centroids.pck, stations_points.csv, runs/<YYYY>, logs).
- Configs are `config/points/config_points_<YYYY>.yml`: copies of config/years with sampling method `points`,
  `CPU_cores: 4` so the NCAR queue keeps its 24, and directory data/points/runs.
- **Decision: no new runner.** `run_year.py` is used unchanged, with `--terrain data/points/terrain --months 1..12`.
  The explicit month list skips the monthly GeoTIFF, which has no meaning for points, and the code the live queue
  runs stays untouched.
- Run: about 7 s per month, 2018-2025 all ok.
- `era5_baseline.py` gained the version `ts_point`. New outputs: points_bias_rmse_recent.png,
  points_skill_recent.png, points_monthly_bias_recent.png, era5_stats_recent_points.csv.

**Result.**
- The point run equals the station-adjusted cluster value within 0.0-0.2 K RMSE at every station; Musala 1.38 vs
  1.37 K. So the clustering (k=1000 in 4 elevation groups) plus the local lapse adjustment costs almost nothing.
- **The valley error is TopoSCALE's own, not the clustering's.** At the valley and low stations, ERA5 t2m with a
  -6.5 K/km correction still beats TopoSCALE, e.g. Boboshevo 1.8 vs 3.4 K, Dabnitsa 1.4 vs 3.2 K, Riltsi 2.3 vs
  3.9 K. The RMSE gap there is larger than the bias gap, so TopoSCALE also follows the day-to-day variation worse
  (free-air temperature).

**Why, from the code** (`topo_scale_zarr.py` ~150-185, same logic as upstream topo_scale.py):
- TopoSCALE temperature is linear interpolation between the two pressure levels that bracket the point's height.
  ERA5 t2m is never used for t. Where the ERA5 orography is above the valley floor, those levels are ERA5's
  underground extrapolation: no surface layer, no cold pools.
- **Vertical fallback.** If a point is below z(1000 hPa) at ANY hour of the period downscaled, then for EVERY
  hour t = the temperature of the lowest level above the point, with no interpolation. Within a monthly run that
  means every hour of the month.
  - It affects 29 of the 1002 clusters (the lowest, Struma/Mesta) in both series, and the Sandanski point.
  - With EDH's 5 levels the "level above" is 925 hPa (~750 m), against 975 hPa with NCAR's 14 levels. This
    probably explains Sandanski -0.3 K (EDH) vs +1.0 K (NCAR).
  - Candidate for Andrei's unreleased "vertical-fallback" fix. Not changed here.

**Next.**
- Decide with the user whether to try a near-surface correction for the valleys, e.g. use ERA5 t2m
  (lapse-corrected) below the ERA5 orography. This is an idea to test; I have not checked what the TopoSCALE
  literature does there.
- The fallback fix needs the same re-downscale as the aspect fix, so both should go into one re-run.

### 2026-11-12 19:07 UTC: NCAR 1962 DONE
ERA5_OK 18:53, downscaled 18:53–19:06. QA hourly OK 12/12. Monthly t_mean GeoTIFF range −11.1..28.2 °C.
The 28.2 °C maximum is the highest NCAR year so far (1963: 27.2), so I checked it against EDH 1962: −11.0..28.2 °C,
the same. The hot July/August 1962 comes from the shared ERA5 forcing, not from a model fault. Accepted.
Lanes now: A 1959, B 1961 (mid-December), C 1960 (late October).

### 2026-11-12 19:41 UTC: NCAR 1961 DONE
ERA5_OK 19:22, downscaled 19:27–19:40. QA hourly OK 12/12, no errors. GeoTIFF range −9.0..25.9 °C (EDH 1961 −9.1..25.9). Accepted.

### 2026-11-12 20:36 UTC: NCAR 1960 DONE
ERA5_OK 20:19, downscaled 20:22–20:35. QA hourly OK 12/12, no errors. GeoTIFF range −8.0..26.0 °C (EDH 1960 −8.1..26.0). Accepted.
25/45 NCAR years done (1960–1984). Downloading: 1959, 1958, 1957.

### 2026-11-13 02:14 UTC: NCAR 1959 DONE
ERA5_OK 01:53, downscaled 02:00–02:13. QA hourly OK 12/12, no errors. GeoTIFF range −9.2..25.5 °C (EDH 1959 −9.3..25.5). Accepted.
26/45 NCAR years done (1959–1984). Downloading: 1958, 1957, 1956.

### 2026-11-13 02:58 UTC: NCAR 1958 DONE
ERA5_OK 02:35, downscaled 02:44–02:57. QA hourly OK 12/12, no errors. GeoTIFF range −9.2..27.5 °C (EDH 1958 −9.2..27.5). Accepted.
27/45 NCAR years done (1958–1984). Downloading: 1957, 1956, 1955.

### 2026-11-13 03:52 UTC: NCAR 1957 DONE
ERA5_OK 03:30, downscaled 03:38–03:51. QA hourly OK 12/12, no errors. GeoTIFF range −8.4..27.0 °C (EDH 1957 −8.5..27.0). Accepted.
28/45 NCAR years done (1957–1984). Downloading: 1956, 1955, 1954.

### 2026-11-13 08:39 UTC: NCAR 1956 DONE
ERA5_OK 08:16, downscaled 08:25–08:38. QA hourly OK 12/12, no errors. GeoTIFF range −12.2..28.5 °C (EDH 1956 −12.2..28.5).
28.5 °C is the warmest monthly-mean pixel of any NCAR year so far, and −12.2 °C the coldest since 1965 (−13.6).
EDH 1956 is identical, so both come from the ERA5 forcing (summer 1956 warm, February 1956 the well-known
extreme cold month in Europe). Accepted.
29/45 NCAR years done (1956–1984). 1955 downscaling; downloading 1954, 1953 (+ next lane).

### 2026-11-13 08:52 UTC: NCAR 1955 DONE
ERA5_OK 08:32, downscaled 08:38–08:51. QA hourly OK 12/12, no errors. GeoTIFF range −6.7..25.3 °C (EDH 1955 −6.6..25.3).
Mildest winter minimum so far (mild winter 1954/55 in the ERA5 forcing; EDH the same). Accepted.
30/45 NCAR years done (1955–1984). Downloading: 1954, 1953, 1952.

### 2026-11-13 09:16 UTC: NCAR 1954 DONE
ERA5_OK 08:59, downscaled 09:02–09:15. QA hourly OK 12/12, no errors. GeoTIFF range −12.6..27.0 °C (EDH 1954 −12.6..27.0).
Cold winter, consistent with the Ihtiman −27 °C hourly observations in January 1954 kept by despike() (LOG 2026-11-12). Accepted.
31/45 NCAR years done (1954–1984). Downloading: 1953, 1952, 1951.

### 2026-11-13 14:15 UTC: NCAR 1953 DONE
ERA5_OK 13:56, downscaled 14:01–14:14. QA hourly OK 12/12, no errors. GeoTIFF range −10.0..26.9 °C (EDH 1953 −10.0..26.9). Accepted.
32/45 NCAR years done (1953–1984). Downloading: 1952, 1951, 1950.

### 2026-11-13 14:38 UTC: NCAR 1952 DONE
ERA5_OK 14:18, downscaled 14:25–14:38. QA hourly OK 12/12, no errors. GeoTIFF range −10.6..30.1 °C (EDH 1952 −10.6..30.1).
30.1 °C is the highest monthly-mean pixel of all NCAR years so far (previous 28.5 in 1956). EDH 1952 is identical, so it
comes from the ERA5 forcing, not from the 14-level run. It is a monthly mean at the warmest low valley pixel; note that
TopoSCALE is warm-biased in the valleys (validation, LOG 2026-11-12), so the true value there was probably lower.
Accepted. 33/45 NCAR years done (1952–1984). 1951 downscaling; downloading 1950, 1949 (+ next lane).

### 2026-11-13 14:52 UTC: NCAR 1951 DONE
ERA5_OK 14:35, downscaled 14:38–14:51. QA hourly OK 12/12, no errors. GeoTIFF range −7.3..27.3 °C (EDH 1951 −7.4..27.3). Accepted.
34/45 NCAR years done (1951–1984). Downloading: 1950, 1949, 1948.

### 2026-11-13 20:30 UTC: NCAR 1950 DONE
ERA5_OK 20:11, downscaled 20:16–20:29. QA hourly OK 12/12, no errors. GeoTIFF range −10.8..28.6 °C (EDH 1950 −10.9..28.6). Accepted.
35/45 NCAR years done (1950–1984). Downloading: 1949, 1948, 1947.

### 2026-11-13 20:53 UTC: NCAR 1948 DONE
ERA5_OK 20:35 (before 1949: lanes finish out of order; run_downscale_all.sh skips years without ERA5_OK and runs
whichever is ready, so this needs no action). Downscaled 20:39–20:52. QA hourly OK 12/12, no errors.
GeoTIFF range −10.7..27.4 °C (EDH 1948 −10.8..27.4). Accepted. 36/45 NCAR years done. 1949 downscaling; downloading 1947, 1946 (+ next lane).

### 2026-11-13 21:06 UTC: NCAR 1949 DONE
ERA5_OK 20:42, downscaled 20:52–21:05. QA hourly OK 12/12, no errors. GeoTIFF range −9.8..24.5 °C (EDH 1949 −9.7..24.5). Accepted.
37/45 NCAR years done (1948–1984). Downloading: 1947, 1946, 1945. Left: 1940–1947.

### 2026-11-14 03:27 UTC: NCAR 1947 DONE
ERA5_OK 03:12, downscaled 03:13–03:26. QA hourly OK 12/12, no errors. GeoTIFF range −12.5..26.5 °C (EDH 1947 −12.6..26.5). Accepted.
38/45 NCAR years done (1947–1984). Downloading: 1946, 1945, 1944. Left: 1940–1946.

### 2026-11-14 04:01 UTC: NCAR 1946 DONE
ERA5_OK 03:37, downscaled 03:47–04:00. QA hourly OK 12/12, no errors. GeoTIFF range −9.7..29.3 °C (EDH 1946 −9.7..29.3).
Warm summer maximum (second after 1952's 30.1); identical in EDH, so it comes from the ERA5 forcing. Accepted.
39/45 NCAR years done (1946–1984). 1945 downscaling; downloading 1944, 1943 (+ next lane).

### 2026-11-14 04:14 UTC: NCAR 1945 DONE
ERA5_OK 03:45, downscaled 04:01–04:14. QA hourly OK 12/12, no errors. GeoTIFF range −11.7..28.1 °C (EDH 1945 −11.7..28.1). Accepted.
40/45 NCAR years done (1945–1984). Downloading: 1944, 1943, 1942. Left: 1940–1944.

### 2026-11-14 10:28 UTC: NCAR 1944 DONE
ERA5_OK 10:13, downscaled 10:14–10:27. QA hourly OK 12/12, no errors. GeoTIFF range −10.4..25.0 °C (EDH 1944 −10.3..24.9). Accepted.
41/45 NCAR years done (1944–1984). 1943 downscaling, 1942 ERA5_OK (queued), downloading 1941 (+ 1940 next).

### 2026-11-14 10:40 UTC: NCAR 1943 DONE
ERA5_OK 10:24, downscaled 10:27–10:40. QA hourly OK 12/12, no errors. GeoTIFF range −10.3..28.4 °C (EDH 1943 −10.4..28.4). Accepted.
42/45 NCAR years done (1943–1984). 1942 downscaling; downloading 1941, 1940 (third lane idle: nothing left to fetch).

### 2026-11-14 10:53 UTC: NCAR 1942 DONE
ERA5_OK 10:27, downscaled 10:40–10:53. QA hourly OK 12/12, no errors. GeoTIFF range −13.4..26.3 °C (EDH 1942 −13.4..26.3).
Coldest monthly-mean pixel since 1965 (−13.6); EDH identical, so it is the ERA5 forcing (the war winters 1940–42 were
very cold in Europe). Accepted. 43/45 NCAR years done (1942–1984). Downloading 1941, 1940.

### 2026-11-14 16:26 UTC: NCAR 1941 DONE
ERA5_OK 16:05, downscaled 16:13–16:26. QA hourly OK 12/12, no errors. GeoTIFF range −10.4..26.4 °C (EDH 1941 −10.5..26.4). Accepted.
44/45 NCAR years done. All ERA5 downloads finished; 1940 (last year) downscaling.

### 2026-11-14 16:39 UTC: NCAR 1940 DONE, NCAR series complete
ERA5_OK 16:04, downscaled 16:26–16:38. QA hourly OK 12/12, no errors. GeoTIFF range −11.7..25.1 °C (EDH 1940 −11.8..25.1). Accepted.
run_downscale_all.sh: "all years done: 86 DONE, 0 FAILED". The download queues A/B/C have exited.
Both series now cover 1940–2025: NCAR (14 levels, data/runs) and EDH (5 levels, data/runs_edh).
Check over the 1940–1984 extension (45 years, 10–12 Nov): every year QA 12/12; no year needed a rerun.
Every monthly GeoTIFF range is within 0.15 K of the EDH run for the same year, at both ends. NCAR and EDH share
the surface forcing and differ only in the pressure levels, so their spatial extremes should agree, and they do.
Extremes of the extension: warmest monthly-mean pixel 30.1 °C (1952), coldest −13.6 °C (1965). Both come from the
forcing (EDH the same).
Next: station_compare.py / station_plots.py / era5_baseline.py rerun for NCAR (now 1940–2025), started 16:40.

### 2026-11-14 ~16:55 UTC: NCAR validation rerun on the full 1940–2025 series
station_compare.py --series ncar, station_plots.py --series ncar and era5_baseline.py --series ncar were rerun
(exit 0). All plots in data/validation/ncar/plots/ were refreshed.
- The extension adds few observations, because the ISD records start late: Musala from 1964-01, Sandanski from
  1959-01. No in-domain station has hourly data for 1940–1958, so those 19 years cannot be checked against stations.
  They are checked only by the QA and by agreement with EDH (LOG entries above).
- Daily t_mean RMSE, long term (K):

  | Station | Raw ERA5 | ERA5 + lapse rate | TopoSCALE, cluster | TopoSCALE, station elevation |
  |---|---|---|---|---|
  | Musala | 10.17 | 3.14 | 1.76 | 1.40 |
  | Sandanski | 2.58 | 1.51 | 2.16 | 2.16 |

  These are practically unchanged from the 1966–2025 numbers (LOG 2026-11-12).
- Decade bias of t_mean (decade_bias.csv, TopoSCALE − obs):
  - Musala: +1.18 K in the 1960s, then +0.63 to +0.93 K.
  - Sandanski: +1.15 K in the 1950s (n=129), then +0.86 to +1.21 K.
  - There is no break or drift when the series is extended back. Sandanski's t_min bias grows slowly
    (+2.9 K in the 1950s/60s to +3.9 K in the 2010s/20s), which is consistent with a valley cold-pool that
    TopoSCALE cannot see. It was already visible before the extension.
- Conclusion unchanged: TopoSCALE adds most at stations above the ERA5 orography, and is worse than ERA5 + lapse rate
  in the low valleys.
Next (open): the azimuth fix and the vertical-fallback fix, then re-downscale both series; validation step 4.

### 2026-11-15: validation on both series, 1940–2025 (NCAR and EDH)
station_compare.py, station_plots.py and era5_baseline.py were run with --series ncar edh (exit 0).
This is the first raw-ERA5 baseline for EDH; the ERA5 baseline is the same file for both, because they share the
surface data. Outputs: data/validation/{ncar,edh}/ and their plots/. Run log: scratchpad val_all.log.
- Daily t_mean RMSE over the full station record (Musala 1964–2025, Sandanski 1959–2025), K:

  | Station | Raw ERA5 | ERA5 + lapse | TopoSCALE, NCAR | TopoSCALE, EDH |
  |---|---|---|---|---|
  | Musala (2925 m) | 10.17 | 3.14 | 1.40 | 1.44 |
  | Sandanski (207 m) | 2.58 | 1.51 | 2.16 | 2.39 |

  TopoSCALE values use the station elevation.
- 2018–2025, 24 stations: TopoSCALE beats ERA5+lapse at 6 stations, in both series: Pletena, Grashevo,
  Obidim, Ortsevo, Malyovitsa, Musala. ERA5+lapse is better at the other 18, mostly low or valley stations.
  NCAR and EDH differ by at most ~0.1 K, except at Sandanski.
- Sandanski: EDH t_mean bias is −0.27 K (NCAR +1.02), but the EDH RMSE is larger. This is compensation, not a better
  model: EDH t_max is −3.3 K (NCAR −2.0) and EDH t_min +2.2 K (NCAR +3.5). The point lies below z(1000 hPa), so the
  vertical fallback takes the lowest level above it: 925 hPa in EDH (5 levels), versus a lower level in NCAR.
  That gives a damped daily cycle. This is further evidence that the vertical-fallback fix is needed.
- Conclusion for both series: TopoSCALE adds value above the ERA5 orography, and the low valleys are its weak spot.
  NCAR ≥ EDH (more levels); the difference matters only below ~1000 hPa.
