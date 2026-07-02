FROM python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    cdo \
    libnetcdf-dev \
    libhdf5-dev \
    && rm -rf /var/lib/apt/lists/*

RUN cdo --version

WORKDIR /app

RUN pip install --no-cache-dir \
    xarray matplotlib pandas scikit-learn netcdf4 h5netcdf pyproj dask cdsapi zarr gcsfs geopandas rasterio

RUN pip install --no-cache-dir git+https://github.com/ArcticSnow/topocalc
RUN pip install --no-cache-dir TopoPyScale

ENV HISTFILE=/root/.bash_history_persist
ENV HISTSIZE=10000
ENV HISTFILESIZE=20000

CMD ["/bin/bash"]