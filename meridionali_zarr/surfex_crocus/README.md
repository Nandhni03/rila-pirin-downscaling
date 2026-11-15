# SURFEX-Crocus test: hydrological year 2024-2025, Southern Carpathians (setup E)

A one-year prototype for the 1981-2025 analysis. No calibration. Made on 10 Nov 2026.

## What was run

| | |
|---|---|
| Forcing | `meridionali_zarr/data/surfex_E/FORCING_2024090100_2025083123.nc`: ERA5 600-1000 hPa, downscaled with TopoPyScale (FABDEM 30 m, topographic horizon, 3001 TopoSUB clusters in 4 elevation groups), exported with `topo_export.to_surfex` (`scripts/export_surfex.py`, 9 Nov). Hourly, 2024-09-01 00 .. 2025-08-31 23 UTC |
| Air temperature | as downscaled by TopoPyScale (ERA5 pressure levels); **no extra lapse rate** (SURFEX `LVERTSHIFT=.FALSE.`) |
| Precipitation | TopoPyScale with `precip_lapse_rate: True` (elevation adjustment on); rain/snow split `continuous` (to_surfex) |
| Model | SURFEX V8.1 (Crocus branch `cen`) in `~/git/surfex/exe`, run with snowtools `s2m research ... -g` (initial ground temperature from the period's mean air temperature) |
| Options | snowtools `OPTIONS_V8.1_NEW_OUTPUTS_NC.nam` unchanged: B21 metamorphism, B92 radiation, VI13 drift, `LSLOPE=.TRUE.`, 50 layers |
| Spin-up / analysis | Sep 2024 = soil spin-up; analysis **2024-10-01 .. 2025-08-31** (forcing ends 31 Aug; Sep 2025 not available) |
| Runs | (1) all 3001 points, 6-hourly output with full profiles (`data/crocus_E/2024-2025/chunk_NN`, 9 Nov, 2.8 min); (2) 24-point subset, **hourly** output, full profiles (`hy2024-2025/subset_hourly`, 37 s; only `XTSTEP_OUTPUT` changed to 3600 s) |
| Subset | 3 points per elevation class (<1000, 1000-1500, 1500-2000, >2000 m) x N / S aspect, slope 10-35 deg, nearest to 800 / 1250 / 1750 / 2200 m (`hy2024-2025/subset_hourly/subset_points.csv`) |

## Scripts (`scripts/`)

- `common.py`: paths, analysis period, point table with elevation and aspect classes.
- `run_subset_hourly.py`: picks the subset, cuts the forcing, writes the hourly namelist, runs s2m.
- `crocus_hy_analysis.py`: daily aggregation, indicators, CSV tables and figures (17 s).
  Run it with `~/TopoPyScale-repo-github/venv/bin/python scripts/crocus_hy_analysis.py`.

## PRO.nc variable names used

`DSN_T_ISBA` (HS, m), `WSN_T_ISBA` (SWE, kg m-2), `SNOMLT_ISBA` (melt rate, kg m-2 s-1), `RAINF_ISBA` (rain, equal to the
forcing), `TG1` (soil 0.5 cm, K). Layer variables: `SNOWDZ` (m), `RSN_VEG` (density), `SNOWTEMP` (K), `SNOWLIQ`
(kg m-3, volumetric), `SNOWTYPE` (MEPRA grain type 0-14). Layer 1 = top; empty layers = NaN.

PRO has **no snowfall variable**, so snowfall and rainfall come from the forcing (`Snowf`, `Rainf`). Open PRO with
`decode_times=False` (`SAG_VEG` has units "days since snowfall"). Time stamps mark the end of each output step.
Fluxes are averages over the step (`LRESETCUMUL=.TRUE.`).

## Indicator definitions

A day D uses the output stamps in (D 00 UTC, D+1 00 UTC]. HS and SWE are daily means; LWC is the daily maximum.

| Indicator | Definition |
|---|---|
| snow day | daily mean HS > 0.05 m |
| snow onset / melt-out | first day of the first run of >= 5 snow days / first snow-free day after the last such run |
| SCD | snow days inside runs of >= 5 days (`SCD_all`: all snow days) |
| peak SWE, date | maximum daily mean SWE, first date |
| melt onset | first day, on or after the peak-SWE date, that starts >= 3 consecutive days of SWE loss > 1 mm/d |
| snowfall, rainfall, solid fraction | forcing sums over the analysis period; snowfall / (snowfall + rainfall) |
| rain-on-snow | rain >= 10 mm/d on SWE >= 10 mm (previous day); consecutive ROS days = 1 event |
| wet snow days | snow days with column LWC = sum(SNOWLIQ x SNOWDZ) > 0 at some output step |
| density at peak | SWE / HS on the peak-SWE day |
| HS > 0.8 m before 31 Jan | days 1 Oct - 31 Jan with daily mean HS > 0.8 m |
| SW_DJF_Wm2 | diagnostic: mean incoming SW of the forcing, Dec-Feb |

> **To confirm:** the 5-day persistence rule above is my assumption of the MODIS definition. Change `PERSIST` and the
> `runs` logic in `indicators()` if the MODIS analysis defines it differently (for example, SCD = all snow days between
> onset and melt-out).

Aspect classes: N = 315-45 deg, S = 135-225 deg, using the aspect TopoPyScale used. Points where that aspect differs by
more than 45 deg from the circular mean of the cluster are excluded from N/S (issue 2).

## Outputs (`hy2024-2025/`)

- `indicators_per_point.csv`: all 3001 points (metadata + indicators).
- `indicators_by_class_aspect.csv`: elevation class x {N, S, all}: n, median, p25 and p75 of every indicator
  (dates as calendar dates).
- `subset_hourly_vs_6hourly.csv`: indicators of the 24 subset points from the hourly vs 6-hourly output.
- `fig_swe_hs_by_class.png`: daily SWE and HS, mean and 25-75 % band, per elevation class, N vs S.
- `fig_indicators_vs_elevation.png`: peak SWE, SCD and bulk density at peak vs elevation, all points.
- `fig_profiles_*.png`: time-height sections (density, temperature, LWC, grain type) for 3 subset points:
  1754 m N, 2213 m N, 2189 m S.
- `checks.txt`: plausibility checks.

## Medians by elevation class (all aspects)

| class | n | onset | peak SWE (mm) | peak date | melt-out | SCD (d) | solid frac. | ROS events | density at peak | days HS>0.8 m before 31 Jan |
|---|---|---|---|---|---|---|---|---|---|---|
| <1000 | 1187 | 17 Feb* | 13 | 21 Feb | 28 Feb* | 9 | 0.07 | 0 | 167 | 0 |
| 1000-1500 | 688 | 21 Nov | 65 | 6 Jan | 12 Mar | 97 | 0.17 | 1 | 283 | 0 |
| 1500-2000 | 563 | 12 Nov | 203 | 3 Mar | 15 Apr | 136 | 0.26 | 3 | 288 | 0 |
| >2000 | 563 | 11 Nov | 416 | 14 Apr | 22 May | 179 | 0.41 | 8 | 356 | 54 |

\* Only the 761 of 1187 points below 1000 m that had any persistent snow.

## Issues observed

1. **N and S slopes are swapped in the TopoPyScale shortwave. This is the main issue; N/S results are not usable yet.**
   - **Code:** `topo_scale(_zarr).py` computes illumination as `cos(solar_azimuth - aspect)`. The solar azimuth there is
     `180 - pvlib azimuth` (0 = south, positive towards east; `solar_geom.py`). The aspect comes from
     `topocalc.gradient_d8` in degrees clockwise from north (`topo_param.py`, `aspect_rad=False`). The two conventions
     differ, so a slope is lit as its N-S mirror (aspect 180 - a): south faces as north and north faces as south.
     East and west are correct.
   - **Data:** mean Dec-Feb incoming SW is 33-48 W m-2 on S-facing points and 78-80 W m-2 on N-facing points in every
     class. As a result, S-facing points have *more* snow than N-facing ones (for example 1500-2000 m: peak SWE 237 vs
     126 mm; melt-out 15 Apr vs 15 Mar).
   - **Scope:** the same line is in every TopoPyScale copy on this machine, including `~/git/TopoPyScale`. It therefore
     affects all downscaled years of setups E and F, not only this test.
   - **Fix:** pass the aspect in the IPW convention (`gradient_d8(..., aspect_rad=True)`, or `pi - aspect` in the
     illumination). The horizon lookup by azimuth should be checked at the same time. Then downscale again (SW only)
     and export again.
2. **Wrong cluster aspect for 387 clusters.** `df_centroids.aspect` is a linear mean of radians, so clusters around
   north average towards south. 387 clusters differ by more than 45 deg from `atan2(aspect_sin, aspect_cos)`, mostly
   north-facing terrain. This aspect drives the illumination in issue 1 and is written to FORCING. These clusters are
   excluded from the N/S classes here, which leaves few N points (87 / 41 / 17 / 36). The fix is a circular mean for
   the cluster aspect.
3. **Summit snow is probably too high.** Peak SWE reaches 1038 mm at 2463 m, and HS reaches 2.6 m. The 12-station test
   of 9 Nov gave Tarcu 187 vs 35 cm observed, Omu 204 vs 104 cm, Balea Lac 110 vs 88 cm. Part of this is wind-exposed
   stations; part is the precipitation elevation adjustment. Oct-Aug precipitation reaches 2075 mm. Compare with
   stations and MODIS before trusting the >2000 m values.
4. **Low elevations have almost no snow.** 426 of 1187 points below 1000 m have no persistent snow; the others have a
   short February episode (median SCD 9 d). 2024-25 was a poor snow winter, but valleys were already too low in the
   station test (Voineasa 5 vs 12 cm).
5. **Wet snow days are high.** The median is 75-108 days above 1000 m, because any LWC > 0 counts, including trace
   water. Hourly output finds 0-12 more wet days than 6-hourly; all other indicators agree within 1 day, 1 mm SWE and
   10 kg m-3. Use hourly output (or an LWC threshold) for wet-snow statistics.
6. **Checked and fine:**
   - The step-like patterns at 800, 1500 and 2000 m in `fig_indicators_vs_elevation.png` are dense columns of clusters
     at the TopoSUB group limits. Medians are continuous across these limits, and so is the forcing (about 0.3 deg C
     per 60 m).
   - There are no NaN values, no snow left on 31 Aug, and no snow-free points above 2000 m (minimum SCD 144 d).
   - Density at peak ranges from 95 to 455 kg m-3. The soil (TG1) ranges from -7 to 35 deg C (daily mean).
7. **SURFEX slope options.** With `LSLOPE=.TRUE.`, SURFEX keeps the direct SW as given, which is correct because
   TopoPyScale already projects it. It multiplies diffuse SW by the slope sky-view factor; this has no effect here
   because to_surfex writes all SW as direct (`SCA_SWdown = 0`). It mixes LW with ground emission
   (`(1 + cos slope) / 2`), and projects precipitation onto the slope.

   TopoPyScale already adds terrain LW (`LW_terrain_contribution: True`), so the terrain LW part is counted twice; the
   effect is probably small. `LSHADOWS_SLOPE` stays off, so there is no second slope or shadow correction of SW.
