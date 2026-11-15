"""Synthetic test of topocalc.gradient_d8 aspect convention, called the way TopoPyScale.topo_param calls it."""
import numpy as np
from topocalc import gradient

n, dx = 21, 30.0
x = np.arange(n) * dx
y_northup = (np.arange(n) * -dx)[::-1][::-1] * -1  # placeholder, replaced below
y_northup = 1000.0 - np.arange(n) * dx              # row 0 = north (GeoTIFF, decreasing y): dy = -30
X, Y = np.meshgrid(x, y_northup)
tilt = np.tan(np.radians(30))
dems = {  # facing direction = direction of steepest DESCENT
    'N-facing': -Y * tilt * -1 * -1,   # elevation increases towards south -> faces north
    'E-facing': -X * tilt,             # decreases towards east
    'S-facing': Y * tilt * -1 * -1 * 1,
    'W-facing': X * tilt,
}
dems['N-facing'] = -(Y - Y.min()) * tilt + 1000   # high in the south (small y) -> descends to north
dems['S-facing'] = (Y - Y.min()) * tilt + 1000    # high in the north -> descends to south
for dy, lab in ((-dx, 'dy<0 (north-up, as topo_param passes it)'), (dx, 'dy>0 (control)')):
    print(f'== {lab}')
    for k, z in dems.items():
        s, a_deg = gradient.gradient_d8(z, dx, dy, aspect_rad=False)
        _, a_ipw = gradient.gradient_d8(z, dx, dy, aspect_rad=True)
        c = (n // 2, n // 2)
        print(f'  {k}: slope {np.degrees(s[c]):5.1f} deg | aspect_rad=False: {a_deg[c]:7.1f} deg '
              f'| aspect_rad=True: {a_ipw[c]:6.3f} rad = {np.degrees(a_ipw[c]):7.1f} deg')
