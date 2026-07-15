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
- **plevels**: `[700,750,775,800,825,850,875,900,925,950,975,1000]` — the 700 hPa level (~3010m) sits safely above the DEM's 2905m peak, satisfying TopoPyScale's documented requirement. Decided not to extend to 600 hPa (not necessary, though harmless if we ever change our minds).
- **Date range**: single day, **2016-08-30**, hourly (ERA5 native timestep) — arbitrary pick within "end of August 2016" per a landslide event in the area; change easily if a more precise date turns up later.
- **Sampling method**: `toposub` only for now (no station points yet — no station data currently in hand; the scraped `stations_list.csv` at the repo root could be added later for validation once the tool is understood).
- **Resolution decision**: run at full 25m resolution (not downsampled), accepting that `compute_dem_param()` / `compute_horizon()` will process the full ~24.4M-pixel buffered DEM and may take a long time. `clustering_mask` (see below) does NOT speed up these two steps — it only affects which pixels become cluster centroids later. If this turns out to be impractically slow in practice, revisit downsampling.
- **n_clusters**: NOT yet decided. Plan is to use TopoPyScale's own built-in `TopoPyScale.topo_sub.search_number_of_clusters()` function (found in the installed source, `topo_sub.py` ~line 157) which scores candidate cluster counts via WCSS, Davies-Bouldin, Calinski-Harabasz, and Elevation RMSE — this is the objective method, not a guess. Given the full DEM has ~24M pixels, we will likely need to run this search on a random subsample of the terrain-parameter dataframe for tractability, then use the selected k for the real full-resolution run.
- **Docker image**: added `gdal-bin` to `docker/Dockerfile` (gives us `gdalinfo`, `ogrinfo`, `gdal_rasterize`, `gdalwarp`, etc. inside the container) — already built and working.
- Regenerate the CDS API key at some point (it was pasted in plaintext into the Claude Code chat transcript during setup — not urgent, just good hygiene): https://cds.climate.copernicus.eu/profile

## Remaining steps (checklist)

- [ ] Confirm TopoPyScale's path convention for `dem.file`/`dem.path` by checking the `filepath` property logic in the installed `topoclass.py` — need this to know whether the DEM must live under `inputs/dem/` specifically (root config.yml's working DEM does) or can stay directly under `inputs/`.
- [ ] Move/organize DEM into `bulgaria_rila_pirin/inputs/dem/` if the convention requires it (currently sits directly in `inputs/`).
- [ ] Rasterize the mask GeoJSON into a `mask.tif` aligned pixel-for-pixel with the DEM (same bounds/resolution) using `gdal_rasterize`, for use as `sampling.toposub.clustering_mask` — restricts which pixels become cluster centroids to the true AOI rather than the buffer.
- [ ] Write `bulgaria_rila_pirin/config.yml` incorporating all the decisions above (adapt from the working root `config.yml` as a template).
- [ ] Write a small standalone script to: instantiate `Topoclass`, run `compute_dem_param()`, take a random subsample of the resulting terrain-parameter dataframe, run `search_number_of_clusters()` over a candidate range, and report the score table — to pick `n_clusters` objectively before committing to a full run.
- [ ] Once `n_clusters` is chosen, write `bulgaria_rila_pirin/pipeline.py` (compute_dem_param → extract_topo_param → compute_solar_geometry → compute_horizon → get_era5 → downscale_climate).
- [ ] Run the pipeline stage by stage inside the container, verifying outputs at each step (this will likely take a while at full 25m resolution — budget real time for `compute_dem_param()`/`compute_horizon()` especially).
- [ ] Extract the downscaled `t` (air temperature) variable at hourly timesteps for 2016-08-30 from the final output and sanity-check it.
