# SurfexCrocus – work log

## 2026-11-09
- Created this folder: `/home/andreiionita27/SurfexCrocus`
  - Command used: `mkdir -p /home/andreiionita27/SurfexCrocus`

## 2026-11-10 – Crocus test HY 2023-2024, Step 1 (inspection only, nothing run)
- Forcing source: setup E stores `meridionali_zarr/data/meridionali_E_{2023,2024}/outputs/downscaled/down.zarr` (3001 clusters, hourly, complete 2023-01-01..2024-12-31); configs `config/config_meridionali_E_{2023,2024}.yml`; metadata `df_centroids.pck`.
- `precip_lapse_rate: True` in both configs (precipitation elevation-adjusted). No extra T lapse rate anywhere.
- No FORCING for 2023-08..2024-09 yet; existing `data/surfex_E/FORCING_2024090100_2025083123.nc` + PRO in `data/crocus_E/2024-2025/` cover HY 2024-25 only.
- SURFEX V8.1 (cen) built 9 Nov: `~/git/surfex/exe/{PGD,PREP,OFFLINE,SODA}`; snowtools `~/git/snowtools`, conda env `surfex`.
- Issue 1: df_centroids `aspect` = linear mean of radians -> 387 clusters off by >45 deg vs atan2(aspect_sin, aspect_cos); north faces lost (N 181 vs circular 729). Written to FORCING aspect.
- Issue 2: to_surfex writes total SW (already slope/horizon-corrected) into DIR_SWdown, SCA_SWdown=0; snowtools namelist has LSLOPE=.TRUE. -> slope projection applied twice (with the wrong aspect). Also affects the 2024-25 run.
- Default output step 21600 s (6-hourly); PRO has RAINF_ISBA but no snowfall variable (take Snowf from FORCING).
- CORRECTION to "Issue 2" above: SURFEX does NOT project the direct SW again (LSHADOWS_SLOPE=.FALSE.; with LSLOPE the direct SW is used as given). LSLOPE only scales diffuse SW (0 here) and LW by (1+cos slope)/2 and projects precipitation.

## 2026-11-10 – Crocus test on HY 2024-2025 (user: "forget about 23-24 for now ... do what I said for 24-25")
- Used the existing forcing + all-points 6-hourly run (data/crocus_E/2024-2025). New: 24-point hourly subset run (`scripts/run_subset_hourly.py` -> `hy2024-2025/subset_hourly/`, 37 s, OFFLINE ENDS CORRECTLY; only XTSTEP_OUTPUT=3600).
- Analysis `scripts/crocus_hy_analysis.py` (common.py) -> `hy2024-2025/` CSVs, figures, checks.txt; README.md written. Analysis period 2024-10-01..2025-08-31.
- MAIN FINDING: TopoPyScale illumination mixes conventions: solar azimuth 0=south (180 - pvlib), aspect from topocalc gradient_d8 clockwise from north -> slopes lit as their N-S mirror. DJF SW: S-facing 33-48, N-facing 78-80 W m-2; S slopes get more snow. Same line in all TopoPyScale copies (incl. ~/git/TopoPyScale) -> affects all downscaled years. Not fixed (needs user decision + SW re-downscaling).
- Hourly vs 6-hourly: indicators within 1 d / 1 mm; wet snow days +0..12 d with hourly.

## 2026-11-10 – SW / aspect diagnosis and fix (full details: aspect_fix/CHANGELOG_aspect_fix.md)
- RETRACTION: the "N/S swap" reported earlier today was my misreading. TopoPyScale aspect is 0 = south, positive east (gradient_d8 on a north-up DEM), the same as solar azimuth and horizon; checked with synthetic DEMs and pvlib. The 2024-25 N/S labels in hy2024-2025/ are therefore swapped (my "S" = terrain N) – to be regenerated.
- Real issues: cluster aspect arithmetic mean (537 clusters in a wrong sector), SW_direct > SWtoa spikes (to 2866 W m-2), sun 30 min late (W > E), to_surfex aspect metadata.
- Fixes committed on branch fix/aspect-azimuth-convention (worktree aspect_fix/TopoPyScale_fix): 5320451, c3cdeda, deaa6a9, 419d085, 21d9f32. Main checkout untouched (the overnight driver uses it).
- 12:29 one-year downscaling with the fix done (meridionali_Efix_2024-09_2024-12, _2025-01_2025-08). Checks: 7 pass, 2 fail -> STOPPED before export/Crocus. (f) fail = pre-existing vertical-interpolation fallback decided over the whole run period (52 low clusters, not the fix); (b) fail = check compares all-sky with clear-sky (clear-hour diagnostic consistent for N and S). Details in aspect_fix/CHANGELOG_aspect_fix.md. Old results relabelled -> hy2024-2025_old_relabelled/.
- 15:20 Fix 5 (user: "let's fix the vertical fallback issue"): commit 0631d84 (+ message bbd0296) on fix/aspect-azimuth-convention: the below-1000-hPa fallback is now decided per time step. Verified on real data (Efix2 runs): period-independent (bit-identical), all other points bit-identical, low points (88-337 m) +0.6 K period mean. Details: aspect_fix/CHANGELOG_aspect_fix.md.

## 2026-11-11 – Parts 3.3 + 4: Crocus HY 2024-25 with the fixed forcing (user: "we should do the 2024-25 crocus comparison first")
- PC shut down ~05:59; nothing of this was running. Download lanes restarted separately (see meridionali_zarr/LOG_28Oct2026.md).
- Disk before start: WSL / 584 GB free, D: 6.1 TB free, C: 261 GB free. Expected use ~60 GB.
- 10:42 started `aspect_fix/scripts/run_comparison_2024-25.sh` (background, log `aspect_fix/logs/comparison_2024-25.log`):
  1 export forcing from Efix2 stores with the fix branch -> `meridionali_zarr/data/surfex_Efix/`
  2 Crocus all 3001 points 6-hourly -> `meridionali_zarr/data/crocus_Efix/2024-2025/`
  3 Crocus all points hourly reduced (wet-snow days) -> `meridionali_zarr/data/crocus_Efix/2024-2025_hourly_reduced/`
  4 24-point hourly profile subset -> `hy2024-2025_fix/subset_hourly/`
  5 analysis (`crocus_hy_analysis.py fix`) + `compare_old_new.py` -> `hy2024-2025_fix/`
  Same options as the old runs; only the forcing differs. All folders new; nothing overwritten.
- 10:57 comparison DONE (all 5 steps exit 0, 15 min). Results `hy2024-2025_fix/` (compare_old_new_by_class_aspect.csv,
  fig_compare_swe_hs_old_new.png, fig_compare_dSWE_vs_dSW.png, profiles, checks.txt). Disk: surfex_Efix 2.6 GB, crocus_Efix 49 GB; / 532 GB free.
  Checks: 0 NaN, no snow left 31 Aug, peak SWE max 1019 mm (1 point), subset vs all-points consistent.
  Effect (medians of per-point change): S-facing DJF SW +11..+17 W m-2 (now 85-88), peak SWE -7..-25 mm at 1000-2000+ m,
  SCD -11 d (1000-1500 S) / -7 d (1500-2000 S), melt-out -1..-3 d; >2000 m S wet-snow days +15. N almost unchanged
  (SW +1.5, SWE -1..-3 mm); E slightly less snow, W slightly more (sun timing fix). Only S had wrong-sector clusters (105-187 per class).
  Waiting for user decision on the full multi-year rerun.
- 12:15 Diagnosis requested by user (read-only; no code/outputs changed). Script + figure + spot table in the session scratchpad
  (diag_aspect.py, aspect_old_vs_new.png, spot_checks.csv). Findings: old figure hy2024-2025/fig_swe_hs_by_class.png used v1
  classes = deg(aspect) read as from-north (TopoPyScale is 0=S,+E -> N/S mirrored) + 'inconsistent' exclusion; v1 counts
  87/275, 41/164, 17/125, 36/130 reproduced exactly; v1 'S' = 640 true-N clusters, v1 'N' = 159 true-S. Separately the old
  forcing had the arithmetic-mean bug: 523 true-S clusters lit as E (214) / N (141) / W (195)... (S kept 181). Spot checks:
  Retezat S cluster 2344 DJF SW 31.7 -> 108.5, Fagaras S 2937 52.2 -> 100.1; N clusters unchanged (32 -> 33.5, 29.4 -> 31.0).
  Use: hy2024-2025_fix figures (+ overlay); old run correctly labelled = hy2024-2025_old_relabelled. Do not use hy2024-2025/.

## 2026-11-12 – Old (pre-fix) Crocus runs deleted (user: "delete the old crocus without the aspect fix")
- Deleted: meridionali_zarr/data/crocus_E/{2024-2025 (26 GB), 2024-2025_hourly_reduced (24 GB), test_12stations_2024-2025 (112 MB)}
  (folder crocus_E removed), hy2024-2025/subset_hourly and hy2024-2025_old_relabelled/subset_hourly (1.2 GB each).
- Kept: old forcing surfex_E/ (2.6 GB), all old result tables/figures (hy2024-2025/, hy2024-2025_old_relabelled/ CSV, PNG,
  daily_hs_swe.nc) and the comparison in hy2024-2025_fix/. Scripts that re-read the old runs (crocus_hy_analysis.py old,
  compare_old_new.py, run_subset_hourly.py old) can no longer be re-run on the old variant.
- 2026-11-13: user "delete the old 2024-2025 6h and hourly runs" -> deleted meridionali_zarr/data/crocus_Efix/2024-2025 (6-hourly,
  23 GB) and 2024-2025_hourly_reduced (24 GB). Replaced by crocus_Efix/2024-2025_3hourly (all variables every 3 h, compressed,
  on D:). Kept: hy2024-2025_fix/ tables, figures, daily_hs_swe.nc and subset_hourly (24-point full hourly, 1.2 GB).
  crocus_hy_analysis.py / compare_old_new.py can no longer re-read those two runs (VARIANTS paths in common.py).
