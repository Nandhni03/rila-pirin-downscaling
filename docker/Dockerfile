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
RUN pip install --no-cache-dir TopoPyScale

# Patch known bugs in TopoPyScale v0.3.3 against modern pandas/numpy:
# (1) raw Python list used where pandas Series expected in default (no-mask) clustering branch
# (2) np.reshape() on an Arrow-backed pandas string column, unsupported by NumPy directly
RUN sed -i 's/mask = \[True\] \* len(df_param)/mask = pd.Series([True] * len(df_param), index=df_param.index)/' \
    /usr/local/lib/python3.13/site-packages/TopoPyScale/topoclass.py && \
    sed -i "s/np.reshape(df_param.point_name.values, shape,order='F')/np.reshape(np.asarray(df_param.point_name, dtype=object), shape, order='F')/g" \
    /usr/local/lib/python3.13/site-packages/TopoPyScale/topoclass.py

ENV HISTFILE=/root/.bash_history_persist
ENV HISTSIZE=10000
ENV HISTFILESIZE=20000
ENV HDF5_USE_FILE_LOCKING=FALSE

CMD ["/bin/bash"]
