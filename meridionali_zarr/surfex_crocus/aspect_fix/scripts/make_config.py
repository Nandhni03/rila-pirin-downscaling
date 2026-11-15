"""Copy a setup-E yearly config for a fix run: only project name, directory, start, end change; the run folder gets
ds_param.nc / da_horizon.nc as hard links and the circular-aspect df_centroids.pck (terrain/).
    python make_config.py <src config> <name> <start> <end>"""
import os, re, shutil, sys
from pathlib import Path
src, name, s, e = sys.argv[1:5]
FIX = Path(__file__).resolve().parents[1]
D = Path.home() / 'TopoPyScale-repo-github/downscaling/meridionali_zarr/data'
out, dst = D / name, FIX / 'config' / f'config_{name}.yml'
assert not out.exists() and not dst.exists(), f'{out} or {dst} exists: not overwritten'
t = Path(src).read_text()
hdr = (f"# {name}: copy of {Path(src).name} for the TopoPyScale fix runs (see ~/SurfexCrocus/aspect_fix/CHANGELOG_aspect_fix.md).\n"
       f"# Changed: name, directory, start, end. Run with PYTHONPATH=~/SurfexCrocus/aspect_fix/TopoPyScale_fix.\n")
for pat, v in ((r'(?m)^(  name: ).*$', name), (r'(?m)^(  directory: )/.*$', str(out)), (r'(?m)^(  start: ).*$', s), (r'(?m)^(  end: ).*$', e)):
    t, n = re.subn(pat, rf'\g<1>{v}', t); assert n == 1, pat
dst.write_text(hdr + t)
T = D / 'meridionali_E_2024' / 'outputs'
(out / 'outputs').mkdir(parents=True)
for f in ('ds_param.nc', 'da_horizon.nc'):
    os.link(T / f, out / 'outputs' / f)
shutil.copy2(FIX / 'terrain' / 'df_centroids_circular.pck', out / 'outputs' / 'df_centroids.pck')
print('config', dst, '-> run folder', out)
