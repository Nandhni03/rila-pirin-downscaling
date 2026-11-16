"""
Station temperature for the validation: one hourly table per station, plus one station list with its place in the
model (pixel, cluster). Only reads; nothing in data/runs* is touched.

Sources
  NOAA ISD (Global Hourly), /data/stations/noaa_isd_hourly/<USAF>-99999-<YYYY>.gz, downloaded 2026-11-11:
      Musala 156150, Sandanski 157120, Ihtiman 156220, Berovo 135980 (the ISD stations inside the domain;
      GHCN-Daily has none). Air temperature = mandatory field TMP (cols 88-92, tenths degC, quality col 93).
      Kept: quality 0 1 4 5 9 A C I M P R U (passed or not checked); dropped: 2 3 6 7 (suspect / erroneous).
      Kept only reports at minute 00 (SYNOP and METAR on the hour); several reports in one hour -> their mean.
      Then despike(): physical limits + isolated spikes against both neighbours (ISD let -55 degC at Musala pass).
  METER.AC (kade.si) nodes, /app/bulgaria_rila_pirin/data/stations_hourly_full_history.csv: hourly mean of the
      5-min readings, labelled with the hour's START (10:00 = 10:00-10:59); kept only coverage == 'complete'.
      The 30 min offset against the model's instantaneous hh:00 is ignored (daily statistics).
Station coordinates/elevation: ISD isd-history (3 decimals), METER.AC selected_stations_metadata.csv.

    python rila_pirin_zarr/scripts/validation/stations_prepare.py
Output (data/validation/): stations.csv, obs_hourly/<id>.csv (time_utc, t_c)
"""
import gzip
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from pyproj import Transformer

R = Path(__file__).resolve().parents[2]
OUT = R / 'data' / 'validation'
ISD_DIR = Path('/data/stations/noaa_isd_hourly')
METER_H = R.parent / 'bulgaria_rila_pirin' / 'data' / 'stations_hourly_full_history.csv'
METER_META = R.parent / 'bulgaria_rila_pirin' / 'data' / 'selected_stations_metadata.csv'
TERRAIN = R / 'data' / 'terrain' / 'outputs'

# from NOAA isd-history.csv (NOAA-musala-meteo-stations/isd-history.csv)
# Musala: isd-history has 3 decimals only (42.183, 23.583 -> a pixel at 2713 m on the steep summit); the
# observatory's position is taken from the METER.AC node N306 on the same summit (2925 m).
ISD = {'156150': ('Musala', 42.17885, 23.58535, 2925.0), '157120': ('Sandanski', 41.550, 23.267, 207.0),
       '156220': ('Ihtiman', 42.433, 23.817, 637.0), '135980': ('Berovo', 41.717, 22.850, 836.0)}
QC_OK = set('01459ACIMPRU')
# despike: (neighbour gap, jump K) pairs; physical limits degC (Bulgaria records -38.3 / +45.2; Musala max ~+19)
SPIKES = ((pd.Timedelta('3h'), 10.0), (pd.Timedelta('6h'), 20.0))
LIMITS = {'default': (-40.0, 46.0), 'Musala': (-40.0, 25.0)}


def despike(h, name):
    """Drop impossible values and isolated spikes. Spike = a reading that differs from BOTH the previous and the
    next reading in the same direction by > 10 K (neighbours <= 3 h away) or > 20 K (<= 6 h away; old 3/6-hourly
    records, where 10 K in 6 h can be a real afternoon peak). Added 2026-11-12: ISD passed Musala -55.0 degC
    (1995-11-20 13 UTC, -16.3 / -17.6 around it) and +29 degC in summer at 2925 m. A first version (> 5 robust
    sigmas from the monthly median) also removed real cold spells (Malyovitsa -15 degC in December, Ihtiman
    -27 degC in Jan 1954) and was replaced: real cold pools build up over hours, spikes do not."""
    h = h.sort_values('time_utc').reset_index(drop=True)
    t, v = h.time_utc, h.t_c
    lo, hi = LIMITS.get(name, LIMITS['default'])
    bad = (v < lo) | (v > hi)
    dp, dn = v - v.shift(1), v - v.shift(-1)
    gp, gn = t - t.shift(1), t.shift(-1) - t
    same = np.sign(dp) == np.sign(dn)
    for gap, jump in SPIKES:
        bad |= same & (gp <= gap) & (gn <= gap) & (dp.abs() > jump) & (dn.abs() > jump)
    if bad.any():
        print(f'  {name}: dropped {bad.sum()} hours: ' +
              ', '.join(f'{x:%Y-%m-%d %H}h {y:+.1f}' for x, y in h.loc[bad, ['time_utc', 't_c']].values[:12]),
              flush=True)
    return h[~bad].reset_index(drop=True)


def read_isd(usaf):
    rows = []
    for f in sorted(ISD_DIR.glob(f'{usaf}-99999-*.gz')):
        with gzip.open(f, 'rt', errors='replace') as fh:
            for line in fh:
                if len(line) < 93 or line[25:27] != '00':
                    continue
                v, q = line[87:92], line[92]
                if v[1:] == '9999' or q not in QC_OK:
                    continue
                rows.append((line[15:25], int(v) / 10.0))
    df = pd.DataFrame(rows, columns=['t', 't_c'])
    df['time_utc'] = pd.to_datetime(df.pop('t'), format='%Y%m%d%H')
    return df.groupby('time_utc').t_c.mean().reset_index()


def main():
    (OUT / 'obs_hourly').mkdir(parents=True, exist_ok=True)
    st = []
    for usaf, (name, lat, lon, z) in ISD.items():
        h = despike(read_isd(usaf), name)
        h.to_csv(OUT / 'obs_hourly' / f'ISD{usaf}.csv', index=False)
        st.append(dict(id=f'ISD{usaf}', name=name, source='NOAA ISD', lat=lat, lon=lon, elev=z))
        print(f'{name}: {len(h)} hours, {h.time_utc.min()} .. {h.time_utc.max()}', flush=True)

    meta = pd.read_csv(METER_META).set_index('NodeID')
    mh = pd.read_csv(METER_H, usecols=['time_utc', 'node', 'temp_c_mean', 'coverage'])
    mh = mh[mh.coverage == 'complete']
    mh['time_utc'] = pd.to_datetime(mh.time_utc, utc=True).dt.tz_localize(None)
    for node, h in mh.groupby('node'):
        if node not in meta.index:
            continue
        m = meta.loc[node]
        h = h.rename(columns={'temp_c_mean': 't_c'})[['time_utc', 't_c']].sort_values('time_utc')
        h = despike(h.reset_index(drop=True), m.Location)
        h.to_csv(OUT / 'obs_hourly' / f'MAC{node}.csv', index=False)
        st.append(dict(id=f'MAC{node}', name=m.Location, source='METER.AC', lat=m.Latitude, lon=m.Longitude,
                       elev=m.Altitude))
    print(f'METER.AC: {mh.node.nunique()} nodes with complete hours', flush=True)

    # place in the model: pixel (EPSG:32634), mask, cluster, pixel and centroid elevation
    st = pd.DataFrame(st)
    ds = xr.open_zarr(TERRAIN / 'ds_param.zarr')
    x, y = Transformer.from_crs(4326, 32634, always_xy=True).transform(st.lon.values, st.lat.values)
    px = ds[['elevation', 'mask', 'point_ind']].sel(x=xr.DataArray(x, dims='s'), y=xr.DataArray(y, dims='s'),
                                                   method='nearest').load()
    inside = (x >= float(ds.x.min())) & (x <= float(ds.x.max())) & (y >= float(ds.y.min())) & (y <= float(ds.y.max()))
    st['x'], st['y'] = x, y
    st['in_domain'] = inside
    st['pixel_elev'] = px.elevation.values
    st['point_ind'] = np.where(inside & (px.point_ind.values >= 0), px.point_ind.values, -1)
    st['in_mask'] = st.point_ind >= 0          # clustered pixel (point_ind -9999 = outside the clustering mask)
    cen = pd.read_pickle(TERRAIN / 'df_centroids.pck').set_index('point_ind')
    ok = st.point_ind >= 0
    st.loc[ok, 'cluster_elev'] = cen.loc[st.point_ind[ok], 'elevation'].values
    st['dz_station_cluster'] = st.elev - st.cluster_elev
    st.to_csv(OUT / 'stations.csv', index=False)
    print(st[['id', 'name', 'elev', 'pixel_elev', 'cluster_elev', 'point_ind', 'in_mask']].round(0).to_string(index=False))


if __name__ == '__main__':
    main()
