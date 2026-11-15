"""
New df_centroids.pck with the circular-mean cluster aspect (fix c3cdeda), WITHOUT re-clustering: same clusters, same
pixel membership (ds_param.nc point_ind), only `aspect` replaced and `aspect_R`, `flat` added. Control: the old
arithmetic mean recomputed from the same pixels must reproduce the old df_centroids.aspect.

    PYTHONPATH=~/SurfexCrocus/aspect_fix/TopoPyScale_fix python make_centroids_circular.py <ds_param.nc> <old df_centroids.pck> <new df_centroids.pck>
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from TopoPyScale import topo_sub as ts

ds_param, old_f, new_f = sys.argv[1:4]
assert not Path(new_f).exists(), f'{new_f} exists: not overwritten'
old = pd.read_pickle(old_f)
with xr.open_dataset(ds_param) as d:
    lab = d.point_ind.values.ravel()
    pix = pd.DataFrame({'cluster_labels': lab, 'aspect': d.aspect.values.ravel(),
                        'aspect_cos': d.aspect_cos.values.ravel(), 'aspect_sin': d.aspect_sin.values.ravel()})
pix = pix[(pix.cluster_labels >= 0) & np.isfinite(pix.aspect)]
lin = pix.groupby('cluster_labels').aspect.mean().reindex(old.point_ind.values)
d_lin = float(np.abs(lin.values - old.aspect.values).max())
print(f'control: old arithmetic mean reproduced from ds_param pixels, max |diff| {d_lin:.2e} rad')
assert d_lin < 1e-6, 'pixel table does not reproduce df_centroids.aspect'
circ = ts.circular_mean_aspect(pix).reindex(old.point_ind.values)
new = old.copy()
new['aspect'] = circ.aspect.values
new['aspect_R'] = circ.aspect_R.values
new['flat'] = new.slope < np.deg2rad(ts.FLAT_SLOPE_DEG)
new['aspect_linear_mean_old'] = old.aspect.values          # kept for comparison
diff = np.degrees(np.abs((new.aspect - old.aspect + np.pi) % (2 * np.pi) - np.pi))
bad = (diff > 45) & ~new.flat
print(f'clusters: {len(new)}; flat (slope < {ts.FLAT_SLOPE_DEG} deg): {int(new.flat.sum())}; aspect changed > 45 deg '
      f'(non-flat): {int(bad.sum())}; > 90 deg: {int(((diff > 90) & ~new.flat).sum())}')
print(f'aspect_R: median {new.aspect_R.median():.3f}, < 0.5: {int((new.aspect_R < 0.5).sum())}')
new.to_pickle(new_f)
print('written', new_f)
