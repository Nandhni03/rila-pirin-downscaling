# Bulgaria Rila-Pirin TopoPyScale run — progress & plan

## How to resume next session

1. Start Docker Desktop / the Docker daemon (however you normally do on this machine).
2. From `rila-pirin-downscaling/`:
   ```bash
   docker compose up -d
   ```
   The image is already built (includes `gdal-bin` now) — this just restarts the existing container, it will NOT rebuild unless the Dockerfile changed again.
3. Get a shell back:
   ```bash
   docker compose exec toposcale bash
   ```
4. Everything under `/app` inside the container is bind-mounted to `rila-pirin-downscaling/` on the host, so **all files (DEM, mask, config.yml, any scripts, any outputs) persist across container/computer restarts automatically** — nothing is lost by shutting down. Only things written *outside* `/app` inside the container (there shouldn't be any) would be lost.
5. Re-read this file top to bottom, then continue from the first unchecked item below.

## Decisions made so far

- **DEM**: `bulgaria_rila_pirin/inputs/rila_pirin_dem_25m_buffered_32634_bilinear_resampling.tif` — EPSG:32634, 25m, 4797×5079 px, elevation range **48m–2905m** (mean ~1035m), geographic extent ~lon 22.79–24.28°E, lat 41.29–42.46°N.
- **Mask** (true AOI, smaller than DEM): `bulgaria_rila_pirin/inputs/mask/rila_pirin_PERFECT_RECTANGLE_32634.geojson` — extent ~lon 22.97–24.09°E, lat 41.43–42.32°N. Confirmed nested correctly inside the DEM (buffer of ~15-20km on all sides).
- **ERA5 area**: NOT manually specified — TopoPyScale docs confirm it's auto-derived from the DEM's own raster bounds (`extent: None — not yet implemented` as a separate config key). No action needed here.
- **ERA5 source**: `cds` (Copernicus CDS API), using the credentials already in `~/.cdsapirc` (mounted read-only into the container at `/root/.cdsapirc`).
- **plevels**: `[600,650,700,750,775,800,825,850,875,900,925,950,975,1000]` — 700 hPa (~3010m) alone already satisfies TopoPyScale's documented requirement (must sit above the DEM's 2905m peak / Musala's 2925m), but extended down to 600 hPa (~4200m) for a more comfortable ~1300m margin, since the cost is negligible for a single-day request.
- **Date range**: single day, **2023-03-15**, hourly (ERA5 native timestep). Superseded the original 2016-08-30 pick (no verified Rila/Pirin-specific event found for 2016 or 2019 — see "Station data" below) — this date instead sits safely in the middle of the verified overlap window (2022-10-25 to 2023-08-16) where multiple METER.AC stations across the elevation range are simultaneously online, per the station data investigation.
- **Sampling method**: `toposub` only for now (station points from METER.AC — see below — could be added later as a `sampling.points` validation set once the tool is understood).

### Station data (for validation)

- Source: **METER.AC** (https://meter.ac), a Bulgarian citizen-sensor network. CC0-licensed, `robots.txt` allows scraping, citable (Terziyski et al., 2020, *Data*, 5(2), 36). Fetch script: `bulgaria_rila_pirin/meteo-data.py`. Cleanup/summary script: `bulgaria_rila_pirin/meteo_data_convert.py` (raw `data.raw.php` dumps have zero-padded strings and bare Unix timestamps — the convert script produces a proper `*_clean.csv` with real UTC + Sofia-local datetime columns, saved next to each raw file in `data/meterac/`).
- **29 of the network's 228 total nodes fall inside the project mask** (verified: both Rila 42.167°N/23.583°E and Pirin 41.717°N/23.450°E reference points confirmed inside the mask bounds; returned node place-names — Musala, Malyovitsa_Hut, Rilski_ezera_Hut, Tevno_ezero_Hut, Makedonia_Hut, Bansko, etc. — corroborate genuine Rila/Pirin coverage).
- **Per-node coverage varies a lot** — nodes did NOT all come online together. Checked so far (4 of the 29):
  - N306 Musala (2925.4m): 2019-08-23 → 2024-04-03
  - N48 Bansko (931.4m): 2018-11-24 → 2023-08-16
  - N235 Boboshevo (375m): 2021-04-18 → still live
  - N27 Semkovo (1622.6m): 2022-10-25 → still live
  - The other 25 AOI nodes have not been checked yet — worth doing before finalizing the validation station set (see checklist).
- Node ID formatting in the metadata CSV is inconsistently zero-padded (`N27`, `N48` vs `N058`, `N306`) — use the exact ID string from the metadata list, don't assume 3-digit padding.
- **Resolution decision**: run at full 25m resolution (not downsampled), accepting that `compute_dem_param()` / `compute_horizon()` will process the full ~24.4M-pixel buffered DEM and may take a long time. `clustering_mask` (see below) does NOT speed up these two steps — it only affects which pixels become cluster centroids later. If this turns out to be impractically slow in practice, revisit downsampling.
- **n_clusters**: NOT yet decided. Plan is to use TopoPyScale's own built-in `TopoPyScale.topo_sub.search_number_of_clusters()` function (found in the installed source, `topo_sub.py` ~line 157) which scores candidate cluster counts via WCSS, Davies-Bouldin, Calinski-Harabasz, and Elevation RMSE — this is the objective method, not a guess. Given the full DEM has ~24M pixels, we will likely need to run this search on a random subsample of the terrain-parameter dataframe for tractability, then use the selected k for the real full-resolution run.
- **Docker image**: added `gdal-bin` to `docker/Dockerfile` (gives us `gdalinfo`, `ogrinfo`, `gdal_rasterize`, `gdalwarp`, etc. inside the container) — already built and working.
- Regenerate the CDS API key at some point (it was pasted in plaintext into the Claude Code chat transcript during setup — not urgent, just good hygiene): https://cds.climate.copernicus.eu/profile
- **Deferred**: decided to purge the old superseded root DEM (`inputs/dem/rila_pirin_DEM_FINAL_32634.tif`, ~93MB) from git history entirely via `git filter-repo` + force-push, to reclaim repo space — ran out of time to do it safely. Steps are known (commit clean state first, `git filter-repo --path inputs/dem/rila_pirin_DEM_FINAL_32634.tif --path inputs/dem/rila_pirin_DEM_FINAL_32634.tif.aux.xml --invert-paths`, re-add remote, `git gc --prune=now --aggressive`, force-push) — pick this up when there's a dedicated block of time, since it rewrites all commit hashes and needs a force-push.

## Remaining steps (checklist)

- [ ] (Optional) Check remaining 25 of 29 AOI METER.AC nodes' coverage windows, in case a better/wider overlap exists; otherwise proceed with the 4 already verified (Musala, Bansko, Boboshevo, Semkovo) as the validation set for `sampling.points`.
- [x] Confirm TopoPyScale's path convention for `dem.file`/`dem.path`: confirmed in `topoclass.py` — if `dem.path` is blank in config.yml, it defaults to `<project.directory>/inputs/dem/`, and critically, if the DEM isn't found there, TopoPyScale will silently try to **auto-download a Copernicus DEM from the internet** instead via `fetch_dem()`. So the DEM MUST live at `inputs/dem/`, not directly under `inputs/`.
- [x] Moved DEM (+ .aux.xml) into `bulgaria_rila_pirin/inputs/dem/`. Mask stays at `inputs/mask/` (untouched, not part of this convention).
- [ ] Rasterize the mask GeoJSON into a `mask.tif` aligned pixel-for-pixel with the DEM (same bounds/resolution) using `gdal_rasterize`, for use as `sampling.toposub.clustering_mask` — restricts which pixels become cluster centroids to the true AOI rather than the buffer.
- [x] Wrote `bulgaria_rila_pirin/config.yml` (adapted from the working root config.yml).
- [x] Ran `compute_dem_param()` (full 25m resolution, ~24.36M pixels, ~13.95M inside mask AOI) — took a while (SVF computation is the slow part) but completed and **cached to `outputs/ds_param.nc`** (won't need to recompute for the real pipeline run).
- [x] Ran TopoPyScale's own `search_number_of_clusters()` (library function, no custom subsampling — full masked population) across k=[100,300,500,700,900]. Results (`n_clusters_search_results` — not saved to a file, just printed; rerun the heredoc from this session's history if needed again):
  ```
  n_clusters   wcss_score  db_score      ch_score  rmse_elevation
         100 1.618099e+07 13.70    736534.78       244.51
         300 1.008343e+07 19.18    446007.63       195.49
         500 8.058977e+06 16.93    357954.56       175.74
         700 6.984001e+06 19.36    299372.90       164.03
         900 6.294301e+06 17.21    261584.92       156.86
  ```
  **Decision: n_clusters = 500.** Reasoning: Davies-Bouldin is non-monotonic/noisy (terrain features are a continuum, not discrete groups — DB isn't a reliable signal here). Calinski-Harabasz decreases monotonically with k as a known mechanical artifact of its formula, not a real "smaller is better" signal — also not reliable. **Elevation RMSE is the metric that matters** (translates ~directly to temperature error via lapse rate) and shows clear diminishing returns: gains of 49m/20m/12m/7m per step — most of the achievable improvement happens by k=500, and it matches the root project's already-tested config for comparability. **STILL NEEDS: update config.yml's n_clusters from 500 (currently already a placeholder value, now also the final decision — but re-verify the line doesn't still say "PLACEHOLDER" in a comment) before writing pipeline.py.**
- [ ] Write a small standalone script to: instantiate `Topoclass`, run `compute_dem_param()`, take a random subsample of the resulting terrain-parameter dataframe, run `search_number_of_clusters()` over a candidate range, and report the score table — to pick `n_clusters` objectively before committing to a full run.
- [ ] Once `n_clusters` is chosen, write `bulgaria_rila_pirin/pipeline.py` (compute_dem_param → extract_topo_param → compute_solar_geometry → compute_horizon → get_era5 → downscale_climate).
- [ ] Run the pipeline stage by stage inside the container, verifying outputs at each step (this will likely take a while at full 25m resolution — budget real time for `compute_dem_param()`/`compute_horizon()` especially).
- [ ] Extract the downscaled `t` (air temperature) variable at hourly timesteps for 2016-08-30 from the final output and sanity-check it.
