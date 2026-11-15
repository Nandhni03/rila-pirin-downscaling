"""Synthetic test of topocalc.horizon azimuth convention on a north-up DEM (row 0 = north), as horizon_batched.py calls it."""
import numpy as np
from topocalc import horizon
n, dx = 101, 30.0
for wall, (r, c) in {'south': (slice(70, 75), slice(None)), 'north': (slice(26, 31), slice(None)),
                     'east': (slice(None), slice(70, 75)), 'west': (slice(None), slice(26, 31))}.items():
    z = np.zeros((n, n)) + 1000.0
    z[r, c] = 1500.0                                   # wall ~600 m from the centre pixel (50, 50)
    out = {}
    for az in (0, 90, 180, -90):
        h = horizon.horizon(az, z, dx)
        out[az] = np.degrees(np.pi / 2 - np.arccos(h[50, 50]))   # same conversion as TopoPyScale
    print(f'wall to the {wall:5s}: horizon angle (deg) at azimuth ' +
          ', '.join(f'{k:+4d}: {v:5.1f}' for k, v in out.items()))
