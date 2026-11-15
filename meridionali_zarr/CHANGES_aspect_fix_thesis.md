# CHANGES – TopoPyScale shortwave / aspect fix (for the thesis methods section)

Date: 11 Nov 2026. Region: Southern Carpathians (Meridionali), setup E (3001 TopoSUB clusters in 4 elevation groups),
ERA5 600–1000 hPa from the Copernicus CDS, years 2011–2025.

## Problems found in the TopoPyScale version used before (fork, commit 7d54b9a)
1. **Cluster aspect averaged arithmetically.** Each cluster's aspect was the plain mean of its pixels' aspect angles.
   Aspect is circular, and in TopoPyScale's convention (0 = south, positive towards east) the mean wraps at south: a
   cluster with pixels facing 10° east and 10° west of south averaged to north. 526 of 2807 non-flat clusters were
   illuminated in the wrong sector; 523 of them truly south-facing (lit as E 214, W 195, N 141). North-, east- and
   west-facing clusters were essentially unaffected.
2. **Direct shortwave above the top-of-atmosphere value** at low sun (up to 2866 W m⁻²) at ~30 clusters, ~70–110 h/yr.
3. **Sun position 30 min late:** solar geometry was taken at the time stamp, while ERA5 radiation is the mean of the
   preceding hour; west-facing slopes received ~10 W m⁻² more winter SW than east-facing ones.
4. **Vertical interpolation fallback decided over the whole run:** a cluster below the 1000 hPa level for a single hour
   used the lowest-level values for the entire period (≈150–200 clusters below ≈340 m; up to 5 K, period-dependent).
5. **SURFEX export metadata:** `to_surfex` wrote aspect in TopoPyScale's internal convention but labelled it
   "degree from north" (N/S mirrored). SURFEX does not use this field in our setup; it only misled the analysis.

The illumination (incidence-angle) formula, the horizon (shading) lookup and the angle conventions of aspect, solar
azimuth and horizon were verified to be mutually consistent (synthetic DEMs, independent pvlib computation) and were
not changed.

## Fix (branch fix/aspect-azimuth-convention, merged into main by fast-forward; main = bbd0296)
| Commit | Change |
|---|---|
| 5320451 | Illumination formula moved, unchanged, into a documented function; unit tests (N/S/E/W synthetic slopes) |
| c3cdeda | Cluster aspect = circular mean, atan2(mean sin, mean cos); resultant length `aspect_R`; `flat` flag (slope < 5°) |
| deaa6a9 | SW_direct capped at SWtoa (port of upstream TopoPyScale 48c07bd) |
| 419d085 | Solar geometry at mid-interval (t − Δt/2) |
| 21d9f32 | `to_surfex` writes aspect as degrees clockwise from north |
| 0631d84, bbd0296 | Below-lowest-level fallback decided per time step (no extrapolation, no lapse rate) |

Cluster membership is unchanged (clustering already used sin/cos of aspect); only the cluster aspect was recomputed.

## Effect
- HY 2024–25 test, median Dec–Feb incoming SW of truly south-facing clusters: 57–62 → 86–88 W m⁻²;
  north-facing ≈ 40 W m⁻² unchanged; E/W difference 12–19 % → 2–4 %.
- Crocus HY 2024–25 (south-facing, median per-point change): peak SWE −7 to −25 mm, snow-cover days −3 to −11 d,
  melt-out −1 to −3 d; north-facing essentially unchanged. Old vs new: ~/SurfexCrocus/hy2024-2025_fix/.
- All years 2011–2025 re-downscaled with bbd0296. Every year: 12/12 months ok, complete hourly time axis, no NaN,
  Dec–Feb SW order S > E, W > N in every elevation class (S 71–91, N 33–47 W m⁻²), SW_direct max 924 W m⁻².
  Year boundaries continuous (largest t step 31 Dec 23 h → 1 Jan 00 h: 0.5–1.2 K; one LW step at 2020/21 is present in ERA5 itself).

## Where
- Outputs: `meridionali_zarr/data/meridionali_E_<year>/outputs/downscaled/{down,daily}.zarr`
- Pre-fix example kept: `meridionali_zarr/data/meridionali_E_2025_pre_aspect_fix/`
- Details: `~/SurfexCrocus/aspect_fix/CHANGELOG_aspect_fix.md`; checks: `meridionali_zarr/data/logs/rerun_fix/`

Suggested sentence: *"Cluster aspect was computed as the circular mean of pixel aspects; solar geometry was evaluated at
the middle of each ERA5 accumulation interval and direct shortwave was capped at its top-of-atmosphere value
(TopoPyScale fork, commit bbd0296)."*
