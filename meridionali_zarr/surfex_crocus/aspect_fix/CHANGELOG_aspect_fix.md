# Shortwave / aspect fix in TopoPyScale: change log

Every code change, why it was made, and how it was checked. Newest steps at the bottom.

## Where the code is

- Imported TopoPyScale (venv `~/TopoPyScale-repo-github/venv`, editable install):
  `~/TopoPyScale-repo-github/fork-original-code/TopoPyScale_Bulgaria_Rila_Pirin_Mountains`, branch `main`, commit
  `7d54b9a` (remote Nandhni03/TopoPyScale_Bulgaria_Rila_Pirin_Mountains). Its `main` checkout is **not touched**.
- Fix branch `fix/aspect-azimuth-convention`: a git worktree of that repository at
  `~/SurfexCrocus/aspect_fix/TopoPyScale_fix`.
  - **Why a worktree:** the overnight driver (`meridionali_zarr/scripts/overnight_E.py`, still running) downscales
    2011..1990 by importing the `main` checkout. Switching branches there would silently change the code for those
    years. My runs import the branch with `PYTHONPATH=~/SurfexCrocus/aspect_fix/TopoPyScale_fix`, checked with
    `TopoPyScale.__file__`.
- `~/git/TopoPyScale` (upstream clone, `e621011`) and the conda envs `tps` and `downscale`: not used by the pipeline,
  not changed.

## Part 1: diagnosis (10 Nov 2026), scripts in `~/SurfexCrocus/aspect_fix/`

| Check | Script | Result |
|---|---|---|
| DEM aspect convention | `test_gradient_convention.py` | `gradient_d8(dem, dx, dy<0)` (north-up GeoTIFF, as `topo_param` calls it) returns degrees with **0 = south, 90 = east, 180 = north, 270 = west**; `aspect_rad=True` gives the same in radians in (-pi, pi]. Only with dy > 0 is it "clockwise from north", as the docstring says |
| Solar azimuth | code (`solar_geom.py`) | `180 - pvlib azimuth`: 0 = south, + east, radians |
| Horizon azimuth | `test_horizon_convention.py` | `topocalc.horizon` on a north-up DEM: a ridge to the south shows at azimuth 0, east at +90: the same reference. The lookup `horizon_for_point` uses degrees of the same azimuth; shading compares radians with radians |
| Independent pvlib check | `pvlib_check.py` (`pvlib_check_old.csv`) | 3 N- and 3 S-facing clusters, 10-20 Dec 2024. N clusters: TopoPyScale direct SW 0-2 W m-2, as pvlib with the 0 = south reading (a north slope cannot see the low sun); the "from north" reading would give 140-165 W m-2. S clusters: 0 impossible hours (pvlib) vs 20 and 55 with the other reading |
| Clustering | `topoclass.py`, `topo_sub.py` | k-means on `aspect_cos`, `aspect_sin` (unit vectors): fine. The centroid `aspect` = `groupby(cluster).mean()` of the pixel aspect in radians: an **arithmetic mean** |
| Upstream | GitHub | Issue #37 (2022): an old `-180` offset reversed N/S; removed in 2022 (c989140), convention since then Dozier (0 = south). Not in our fork. Commit `48c07bd` (5 Nov 2026): SW_direct > SWtoa spikes. Commit `fe8e5e0`: precip `{}` bug, already fixed in our fork (`topo_scale_zarr.py` header, line 19) |

**Conclusion: no N/S swap.** The illumination, solar azimuth and horizon share one convention. The DJF SW order
*by the aspect TopoPyScale used* is S 78-80 > W 63-72 > E 53-59 > N 34-45 W m-2 in every class.

The earlier "swap" came from reading `aspect` as degrees from north. `to_surfex` writes it that way in FORCING, and my
analysis of 10 Nov read it that way too. Real problems found:

1. **Cluster aspect = arithmetic mean of angles.** With 0 = south it wraps at south: clusters facing roughly south
   average towards north and are illuminated in the wrong sector. 537 clusters (of 3001, slope >= 5 deg) are in a
   different sector than their terrain: 526 terrain-S clusters lit as E (206), W (189) or N (131).
2. **SW_direct > SWtoa near sunrise/sunset** (upstream bug): SW_direct up to 2241 W m-2 (2024) and 2866 W m-2 (2025),
   70 and 104 hours on 28 and 34 clusters.
3. **Sun 30 min late.** ERA5 SW at stamp t = mean over (t-1h, t]; the sun was computed at t. Store check: hourly SW
   correlates best with clear-sky GHI at t - 30 min (0.963 vs 0.960 at t, 0.945 at t - 60 min); the daily SW centroid
   is 0.32 h after transit. Effect: W > E by about 10 W m-2 in DJF.
4. **`to_surfex` aspect metadata:** written as "degree from north" but it is 0 = south. SURFEX does not use it for
   radiation (`LSHADOWS_SLOPE=.FALSE.`), so the simulation is not affected, but the FORCING metadata was wrong.

## Part 2: commits on `fix/aspect-azimuth-convention`

| Commit | Files | What and why |
|---|---|---|
| `5320451` | `solar_geom.py`, `topo_scale.py`, `topo_scale_zarr.py`, `tests/test_sw_geometry.py` | Illumination formula moved **unchanged** into `solar_geom.cos_illumination()`, with the conventions documented; added `aspect_to_bearing_deg()`. Why: one tested place for the geometry. New tests (synthetic 30 deg slopes, 45.5 N, 21 Dec): aspect and azimuth references, S lit and N self-shadowed at noon, E/W symmetric morning/afternoon, horizon reference. The existing `test_topo_scale_zarr_parity.py` still passes (numbers unchanged) |
| `c3cdeda` | `topo_sub.py`, `topoclass.py`, `topo_param.py`, test | **Fix 1.** `topo_sub.circular_mean_aspect()`: cluster aspect = atan2 of the mean pixel sin/cos; new columns `aspect_R` (resultant length, 0..1) and `flat` (mean slope < 5 deg). Same fix for `extract_pts_param` idw/linear. Clustering unchanged (uses sin/cos), so **cluster membership does not change** |
| `deaa6a9` | `topo_scale_zarr.py`, `topo_scale.py` | **Fix 2.** `SW_direct` capped at `SWtoa` before Beer's law (port of upstream `48c07bd`) |
| `419d085` | `solar_geom.py`, test | **Fix 3.** `get_solar_geom(mid_interval=True)`: sun at t - tstep/2, labels kept at t. `mid_interval=False` restores the old behaviour |
| `21d9f32` | `topo_export.py` | **Fix 4.** `to_surfex` writes aspect as degrees clockwise from north, with a corrected attribute |

Not changed: temperature (no lapse rate added) and precipitation settings or formulas.

## Part 3: one-year verification run (Sep 2024 - Aug 2025), set-up

New files only; nothing existing was overwritten or deleted.

| Step | What | Why |
|---|---|---|
| `aspect_fix/scripts/make_centroids_circular.py` -> `aspect_fix/terrain/df_centroids_circular.pck` | Old df_centroids with `aspect` replaced by the circular mean of the cluster pixels (`ds_param.nc` point_ind, aspect_cos/sin, with the new `topo_sub.circular_mean_aspect`); new `aspect_R`, `flat`, and `aspect_linear_mean_old` kept | Same clusters, so old and new are comparable cluster by cluster; re-clustering is not needed because clustering uses sin/cos. Control: the old arithmetic mean recomputed from the same pixels reproduces the old aspect exactly (max diff 0.0). 363 non-flat clusters change > 45 deg (225 > 90 deg); 194 flat; aspect_R median 0.95 |
| `aspect_fix/config/config_meridionali_Efix_2024-09_2024-12.yml`, `..._2025-01_2025-08.yml` | Copies of config_meridionali_E_2024/2025.yml; only name, project directory, start, end changed | ERA5 stores are per calendar year |
| `meridionali_zarr/data/meridionali_Efix_2024-09_2024-12/`, `..._2025-01_2025-08/` | New project folders: `ds_param.nc`, `da_horizon.nc` hard links (as overnight_E.py does), `df_centroids.pck` = the circular one; `ds_solar.nc` recomputed by the fixed code | TopoPyScale re-saves ds_param.nc as a new file (checked: new inode, the shared original is untouched) |
| `aspect_fix/scripts/run_downscale_fix.sh` | `run_year_public.py <config> --stop-after downscale` with `PYTHONPATH` = fix worktree; log `aspect_fix/logs/downscale_*.log` | The log records branch, commit and `TopoPyScale.__file__` (checked: worktree, 21d9f32) |
| `aspect_fix/scripts/crocus_parallel_nam.py` | Copy of `crocus_parallel.py` plus `--namelist` | The original is not modified |
| `aspect_fix/namelists/OPTIONS_hourly_reduced.nam` | snowtools default with `XTSTEP_OUTPUT=3600` and `CSELECT` limited to HS, SWE, rain, melt, SNOWDZ, SNOWLIQ | Hourly wet-snow days (LWC > 0.5 % vol) for all 3001 points at ~22 GB instead of ~150 GB. Tested on 24 points: HS identical to the full-output run |
| `~/SurfexCrocus/scripts/*_v1_backup_20261110.py` | v1 analysis scripts kept | v2 replaces them |
| `scripts/common.py` v2 | Variants old/fix; aspect classes from the terrain aspect as a compass bearing, flat excluded; same classes for both variants | v1 read aspect as degrees from north (N/S swapped) |
| `scripts/run_subset_hourly.py` v2 | Subset re-picked (3 per class x N/S, slope 10-35 deg, aspect_R > 0.8) -> `aspect_fix/subset_points.csv`, used for both variants | Profiles compare the same clusters |
| `scripts/crocus_hy_analysis.py` v2 | Argument old/fix; `wet_snow_days_hourly` (LWC > 0.5 % vol in any layer, hourly); v1 wet days kept as `wet_snow_days_any_6h`; E, W and flat rows in the table; saves daily HS/SWE | Requested comparison |
| `scripts/compare_old_new.py` | Old vs new table per class x aspect and figures | Part 4 |
| `hy2024-2025/` (v1 results of 10 Nov) | Kept as is | Its N/S labels are swapped: see `hy2024-2025_old_relabelled/` |

## Part 3: one-year run and checks (10 Nov 2026, 11:59-12:29)

Downscaling with the fix: Sep-Dec 2024 (5 min) and Jan-Aug 2025 (13 min), 3001 points each, 0 failed, exit 0. Logs:
`aspect_fix/logs/downscale_*.log`. Imported module: worktree, branch `fix/aspect-azimuth-convention`, `21d9f32`.
Checks: `aspect_fix/scripts/check_fix.py` -> `aspect_fix/checks/` (`check_summary.txt`, `sw_DJF_*.csv`, `sw_JUN_*.csv`,
`pvlib_check_old_vs_new.csv`, `horizon_check.csv`).

| Check | Result |
|---|---|
| (a) unit tests | PASS, 7/7 (`tests/test_sw_geometry.py`); repo parity test 4/4 |
| SW cap | PASS: SW_direct max 2866 -> 924 W m-2; hours > 1361 W m-2: 112 -> 0; no NaN |
| (c) DJF SW order | PASS: S 85-88 > E 60-66 ~ W 58-68 > N 35-46 W m-2 in every class |
| (c) E ~ W | PASS: \|W-E\|/mean 2-4 % (old 12-19 %) |
| (d) June vs DJF | PASS: relative S-N difference 7-15 % in June vs 59-86 % in DJF |
| (e) horizon | PASS: 2 deepest clusters (max horizon 59 and 56 deg): 0 h of direct SW while horizon > sun; shading agrees with the stored horizon 99.6 % of sun-up hours (N/S-mirrored horizon: 74-79 %) |
| (g) aspect consistency | PASS: clusters > 45 deg from their k-means centroid direction: 363 -> 0 (non-flat); 194 flat; 3 with aspect_R < 0.5 |
| (b) pvlib | **FAIL as specified.** All-sky TopoPyScale SW vs clear-sky pvlib POA cannot give similar bias for N (diffuse only in December) and S. Correlation N 0.96, S 0.78 (criterion: within 0.15). Diagnostic on clear hours only (`scripts/pvlib_clear_hours.py`, `checks/pvlib_clear_hours_direct.csv`), direct beam on the slope: N corr 0.98-0.99; S corr 0.83-0.96 (old 0.78-0.89), S direct 305-364 W m-2 (old 100-163). TopoPyScale direct is 28-37 % below the pvlib clear-sky beam on both N and S clusters: a level offset of the ERA5 direct/diffuse partition, not geometry |
| (f) non-SW variables | **FAIL.** Jan-Aug 2025: all variables bit-identical. Sep-Dec 2024: t, q, p, u, v, wd, LW differ (t up to 5.3 K) at 52 low clusters (288-339 m, group 1), every hour; tp identical. **Cause (pre-existing, not the fix):** `topo_scale_zarr.downscale_point` uses `if (row.elevation < z_1000hPa).sum():`, so if a point is below the 1000 hPa surface in any single hour of the run period, its whole series takes the "no vertical interpolation" fallback (values of the level above). Old full-year 2024 run: 199 points in fallback; new Sep-Dec run: 147 (difference = the 52); 2025 both 187. Results of low points therefore depend on the period downscaled, and the branch can switch between yearly runs |

Stopped here as instructed (a check failed): no SURFEX export and no Crocus rerun with the fixed forcing yet. Done before
stopping: old-forcing hourly reduced Crocus run (`data/crocus_E/2024-2025_hourly_reduced`, 24 GB, 12/12 OK), old
subset with the re-picked points, and the old results relabelled with correct aspect classes
(`hy2024-2025_old_relabelled/`).

## Fix 5: vertical-interpolation fallback per time step (10 Nov 2026, on your request "let's fix the vertical fallback issue")

| Commit | Files | What and why |
|---|---|---|
| `0631d84` | `topo_utils.py` (new `vertical_interp_plev`), `topo_scale_zarr.py`, `topo_scale.py`, `tests/test_vertical_interp.py` | **Before:** `if (row.elevation < z_lowest_level).sum():` sent a point's whole series to the no-interpolation branch (values of the lowest level) if the point was below the lowest pressure level at any single time step of the run. So low clusters depended on the period downscaled (2024: 199 points in fallback as a full year, 147 for Sep-Dec alone; t up to 5.3 K different) and could switch between yearly runs. **Now:** per time step, linear interpolation between the nearest levels below and above; lowest-level values only at the steps when the point is below every level. No extrapolation, no lapse rate. Interpolated steps are bit-identical to the former code; continuous at the switch. Both downscalers changed, so the zarr-vs-classic parity test still holds. The `level` coordinate is no longer carried, so `drop_vars(['level'])` is made tolerant (`errors='ignore'`) |

Tests: `tests/test_vertical_interp.py` 5/5 (bit-identity with the former branch, fallback only at the steps below,
independence of the period, continuity, error above all levels); parity 4/4; geometry 7/7. `test_clustering_mask.py`
errors with an HDF5 file-lock error on **both main and the branch** (pre-existing, in the test fixture); with
`HDF5_USE_FILE_LOCKING=FALSE` it passes 2/2 on both.

Real-data verification: new runs with 0631d84 in `meridionali_Efix2_2024-09_2024-12`, `meridionali_Efix2_2025-01_2025-08`
and `meridionali_Efix2_2024-01_2024-12` (full 2024, for the period-independence check), created by
`aspect_fix/scripts/make_config.py`, run by `aspect_fix/scripts/run_downscale_names.sh`, checked by
`aspect_fix/scripts/check_fallback.py`.

Real-data verification of 0631d84 (`aspect_fix/checks/fallback_summary.txt`, `fallback_points.csv`,
`fallback_summary_by_period.csv`). All runs exit 0, 0 failed points.

| Check | Result |
|---|---|
| Period independence | PASS: Sep-Dec 2024 downscaled alone == the same months inside full-year 2024, all 12 variables bit-identical (before the fix: t up to 5.3 K different at 52 points) |
| Points never below the lowest level | PASS: 2854 (Sep-Dec 2024) and 2814 (Jan-Aug 2025) points bit-identical to the previous run (Efix), all variables |
| Points with steps below | PASS: same set as the former whole-period fallback (147 / 187 points, 88-337 m); only steps above the lowest level changed |
| Size of the change at those points | Below the lowest level 6.5-17 % of the hours (median; max 87 %). Formerly forced hours are now interpolated: period-mean t +0.6 K (median; range +0.2 to +1.0 K), single hours up to 5.4 K (2024) / 7.3 K (2025) |
| Complete, no NaN | PASS (2928 h and 5832 h) |

`bbd0296`: wording of the end-of-run message only ("fallback at those hours only"). Parity and vertical tests still pass.
