"""Shared paths and point classification for the Crocus HY 2024-2025 test (setup E, 3001 TopoSUB clusters)."""
from pathlib import Path

import numpy as np
import pandas as pd

MZ = Path.home() / 'TopoPyScale-repo-github' / 'downscaling' / 'meridionali_zarr'
FORCING = MZ / 'data' / 'surfex_E' / 'FORCING_2024090100_2025083123.nc'
CENTROIDS = MZ / 'data' / 'meridionali_E_2024' / 'outputs' / 'df_centroids.pck'
RUN_ALL = MZ / 'data' / 'crocus_E' / '2024-2025'          # 12 chunks, 6-hourly PRO, all points (run 9 Nov 2026)
OUT = Path(__file__).resolve().parents[1] / 'hy2024-2025'

ANALYSIS_START, ANALYSIS_END = '2024-10-01', '2025-08-31'   # forcing ends 2025-08-31 23 UTC; Sep 2024 = spin-up

ELEV_BINS = [-np.inf, 1000, 1500, 2000, np.inf]
ELEV_LABELS = ['<1000', '1000-1500', '1500-2000', '>2000']


def points():
    """One row per forcing point (same order as FORCING Number_of_points): elevation, slope, aspect, classes.

    aspect_deg: the aspect TopoPyScale used for illumination and wrote to FORCING (df_centroids.aspect).
    aspect_circ: circular mean atan2(aspect_sin, aspect_cos). df_centroids.aspect is a linear mean of radians, so for
    clusters around north it can be off by up to 180 deg. Points where the two differ by > 45 deg are flagged
    aspect_ok=False and get no N/S class (their simulated radiation corresponds to a different slope than the terrain).
    """
    df = pd.read_pickle(CENTROIDS)
    a = np.degrees(df.aspect.values) % 360
    c = np.degrees(np.arctan2(df.aspect_sin.values, df.aspect_cos.values)) % 360
    diff = np.abs((a - c + 180) % 360 - 180)
    out = pd.DataFrame({
        'point': np.arange(len(df)), 'point_ind': df.point_ind.values,
        'elevation': df.elevation.values, 'slope_deg': np.degrees(df.slope.values),
        'aspect_deg': a, 'aspect_circ': c, 'aspect_diff': diff, 'aspect_ok': diff <= 45,
        'lat': df.lat.values, 'lon': df.lon.values})
    out['elev_class'] = pd.cut(out.elevation, ELEV_BINS, labels=ELEV_LABELS)
    sect = np.where((a >= 315) | (a < 45), 'N', np.where((a >= 135) & (a < 225), 'S',
                    np.where((a >= 45) & (a < 135), 'E', 'W')))
    out['aspect_class'] = np.where(out.aspect_ok, sect, 'inconsistent')
    return out
