FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    cdo \
    gdal-bin \
    libnetcdf-dev \
    libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

RUN cdo --version
RUN gdalinfo --version

WORKDIR /app

RUN pip install --no-cache-dir \
    xarray matplotlib pandas scikit-learn netcdf4 h5netcdf pyproj dask cdsapi zarr gcsfs geopandas rasterio

RUN pip install --no-cache-dir git+https://github.com/ArcticSnow/topocalc
# Pinned: every sed/python patch below targets exact line text in 0.3.3.
# An unpinned upgrade could silently stop matching (patch no-ops) or, worse,
# match something unintended in a rewritten function.
RUN pip install --no-cache-dir TopoPyScale==0.3.3

# Patch known bugs in TopoPyScale v0.3.3 against modern pandas/numpy (found and
# fixed live across two debugging sessions — 2026-08-06/07 and 2026-08-13 — and
# baked in here so they survive an image rebuild instead of only living in the
# running container; see bulgaria_rila_pirin/PROGRESS.md for full bug writeups):
# (1) raw Python list used where pandas Series expected in default (no-mask) clustering branch
# (2) np.reshape() on an Arrow-backed pandas string column, unsupported by NumPy directly
RUN sed -i 's/mask = \[True\] \* len(df_param)/mask = pd.Series([True] * len(df_param), index=df_param.index)/' \
    /usr/local/lib/python3.13/site-packages/TopoPyScale/topoclass.py && \
    sed -i "s/np.reshape(df_param.point_name.values, shape,order='F')/np.reshape(np.asarray(df_param.point_name, dtype=object), shape, order='F')/g" \
    /usr/local/lib/python3.13/site-packages/TopoPyScale/topoclass.py

# (3) Bug #6: topo_scale.py's tstep_dict is uppercase-only ('1H'/'3H'/'6H'), but
#     modern pandas rejects uppercase 'H' in pd.date_range(freq=...), forcing
#     config.yml's timestep to lowercase ('1h') — which then misses this dict
#     entirely and silently divides by None. Add lowercase aliases.
RUN sed -i "s/tstep_dict = {'1H': 1, '3H': 3, '6H': 6}/tstep_dict = {'1H': 1, '3H': 3, '6H': 6, '1h': 1, '3h': 3, '6h': 6}/" \
    /usr/local/lib/python3.13/site-packages/TopoPyScale/topo_scale.py

# (4) Bug #7: chained assignment (df[col].loc[mask] = value) silently writes to
#     a throwaway copy under pandas >=3.0's mandatory Copy-on-Write, leaving
#     point_name stuck at its '-9999' default for every row.
RUN python3 -c "\
import pathlib; \
p = pathlib.Path('/usr/local/lib/python3.13/site-packages/TopoPyScale/topoclass.py'); \
old = \"df_param['point_name'].loc[~df_param.cluster_labels.isnull()] = df_param.cluster_labels.loc[~df_param.cluster_labels.isnull()].astype(int).astype(str).str.zfill(n_digits)\"; \
new = \"not_null = ~df_param.cluster_labels.isnull()\n            df_param.loc[not_null, 'point_name'] = df_param.loc[not_null, 'cluster_labels'].astype(int).astype(str).str.zfill(n_digits)\"; \
text = p.read_text(); \
assert old in text, 'Bug #7 patch target not found — TopoPyScale source may have changed'; \
p.write_text(text.replace(old, new))"

# (5) Bug #9: fetch_era5.py has its OWN separate uppercase-only time_step_dict
#     ('1H'/'3H'/'6H') used to build the CDS API request's 'time' field —
#     identical case-sensitivity issue to Bug #6/#3, different file, different
#     function. With timestep: 1h, this silently returned None for the 'time'
#     field, causing a CDS 400 Bad Request on every fresh (uncached) download.
RUN sed -i "/'6H': \['00:00', '06:00', '12:00', '18:00'\]}/a\\    time_step_dict.update({'1h': time_step_dict['1H'], '3h': time_step_dict['3H'], '6h': time_step_dict['6H']})" \
    /usr/local/lib/python3.13/site-packages/TopoPyScale/fetch_era5.py

# (6) Bug #11: topo_param.py's extract_pts_param() (point-mode only — never
#     exercised by the toposub full-grid path) initializes elevation/slope/
#     aspect/svf columns with integer 0, so pandas infers int64; a later
#     per-point float assignment then hits pandas 3.0's strict type-checking
#     and raises instead of upcasting.
RUN sed -i "s/df_pts\[\['elevation', 'slope', 'aspect', 'aspect_cos', 'aspect_sin', 'svf'\]\] = 0$/df_pts[['elevation', 'slope', 'aspect', 'aspect_cos', 'aspect_sin', 'svf']] = 0.0/" \
    /usr/local/lib/python3.13/site-packages/TopoPyScale/topo_param.py

ENV HISTFILE=/root/.bash_history_persist
ENV HISTSIZE=10000
ENV HISTFILESIZE=20000
ENV HDF5_USE_FILE_LOCKING=FALSE

CMD ["/bin/bash"]
