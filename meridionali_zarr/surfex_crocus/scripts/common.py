"""Shared paths and point classification for the Crocus HY 2024-2025 test (setup E, 3001 TopoSUB clusters).

v2 (10 Nov 2026): two variants of the same test, `old` (forcing from TopoPyScale main 7d54b9a) and `fix` (forcing from
branch fix/aspect-azimuth-convention, see ~/SurfexCrocus/aspect_fix/CHANGELOG_aspect_fix.md).

Aspect: TopoPyScale stores it in radians with 0 = SOUTH, positive towards east (Dozier/IPW). v1 of this file read it
as degrees from north, which swapped the N and S classes. Classes now come from the TERRAIN aspect (circular mean of
the cluster pixels, aspect_fix/terrain/df_centroids_circular.pck), converted to a compass bearing, for both variants,
so old and new results are compared on the same clusters. Clusters with slope < 5 deg are 'flat' (no aspect class).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MZ = Path.home() / 'TopoPyScale-repo-github' / 'downscaling' / 'meridionali_zarr'
CENTROIDS_TERRAIN = ROOT / 'aspect_fix' / 'terrain' / 'df_centroids_circular.pck'
CENTROIDS_OLD = MZ / 'data' / 'meridionali_F_2025' / 'outputs' / 'df_centroids_pre_aspect_fix.pck'   # 11 Nov: was meridionali_E_2024 (re-downscaled); same table
SUBSET = ROOT / 'aspect_fix' / 'subset_points.csv'

VARIANTS = {
    'old': dict(forcing=MZ / 'data' / 'surfex_E' / 'FORCING_2024090100_2025083123.nc',
                run_all=MZ / 'data' / 'crocus_E' / '2024-2025',                       # 6-hourly, full output
                run_hourly=MZ / 'data' / 'crocus_E' / '2024-2025_hourly_reduced',     # hourly, HS/SWE/LWC only
                out=ROOT / 'hy2024-2025_old_relabelled'),
    'fix': dict(forcing=MZ / 'data' / 'surfex_Efix' / 'FORCING_2024090100_2025083123.nc',
                run_all=MZ / 'data' / 'crocus_Efix' / '2024-2025',
                run_hourly=MZ / 'data' / 'crocus_Efix' / '2024-2025_hourly_reduced',
                out=ROOT / 'hy2024-2025_fix'),
}

ANALYSIS_START, ANALYSIS_END = '2024-10-01', '2025-08-31'   # forcing ends 2025-08-31 23 UTC; Sep 2024 = spin-up

ELEV_BINS = [-np.inf, 1000, 1500, 2000, np.inf]
ELEV_LABELS = ['<1000', '1000-1500', '1500-2000', '>2000']
FLAT_SLOPE_DEG = 5.0


def bearing(aspect_rad):
    """TopoPyScale aspect (rad, 0 = south, positive towards east) -> compass bearing (deg clockwise from north)."""
    return (180.0 - np.degrees(aspect_rad)) % 360.0


def sector(b):
    return np.where((b >= 315) | (b < 45), 'N', np.where(b < 135, 'E', np.where(b < 225, 'S', 'W')))


def points():
    """One row per forcing point (same order as FORCING Number_of_points)."""
    df = pd.read_pickle(CENTROIDS_TERRAIN)
    old = pd.read_pickle(CENTROIDS_OLD)
    assert (df.point_ind.values == old.point_ind.values).all()
    out = pd.DataFrame({
        'point': np.arange(len(df)), 'point_ind': df.point_ind.values,
        'elevation': df.elevation.values, 'slope_deg': np.degrees(df.slope.values),
        'bearing': bearing(df.aspect.values),                  # terrain aspect (circular mean)
        'bearing_used_old': bearing(old.aspect.values),        # what the old downscaling illuminated
        'aspect_R': df.aspect_R.values, 'flat': df.flat.values,
        'lat': df.lat.values, 'lon': df.lon.values})
    out['elev_class'] = pd.cut(out.elevation, ELEV_BINS, labels=ELEV_LABELS)
    out['aspect_class'] = np.where(out.flat, 'flat', sector(out.bearing))
    out['old_sector_differs'] = (sector(out.bearing_used_old) != sector(out.bearing)) & ~out.flat
    return out
