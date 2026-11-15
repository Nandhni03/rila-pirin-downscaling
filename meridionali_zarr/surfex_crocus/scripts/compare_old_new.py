"""
Old vs fixed TopoPyScale shortwave: Crocus HY 2024-2025 indicators per elevation class x aspect, and SWE/HS figure.

Same clusters and same aspect classes (terrain aspect, compass bearing) for both; only the forcing differs
(old: TopoPyScale main 7d54b9a; fix: branch fix/aspect-azimuth-convention). Run after
`crocus_hy_analysis.py old` and `crocus_hy_analysis.py fix`.

    ~/TopoPyScale-repo-github/venv/bin/python scripts/compare_old_new.py
Outputs in hy2024-2025_fix/: compare_old_new_by_class_aspect.csv, fig_compare_swe_hs_old_new.png,
fig_compare_dSWE_vs_dSW.png
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ELEV_LABELS, VARIANTS  # noqa: E402
from crocus_hy_analysis import C_GREY, C_N, C_S, INK  # noqa: E402  (also applies the rcParams)

OUT = VARIANTS['fix']['out']
COLS = {'SW_DJF_Wm2': 'DJF SW (W m-2)', 'peak_SWE_mm': 'peak SWE (mm)', 'SCD': 'SCD (d)',
        'melt_out': 'melt-out', 'wet_snow_days_hourly': 'wet-snow days (LWC>0.5 %, hourly)'}


def load(v):
    d = pd.read_csv(VARIANTS[v]['out'] / 'indicators_per_point.csv', parse_dates=['melt_out'])
    d['melt_out_doy'] = (d.melt_out - pd.Timestamp('2024-10-01')).dt.days
    return d


def main():
    o, n = load('old'), load('fix')
    assert (o.point_ind.values == n.point_ind.values).all() and (o.aspect_class.values == n.aspect_class.values).all()
    rows = []
    for ec in ELEV_LABELS:
        for ac in ('N', 'E', 'S', 'W'):
            m = ((n.elev_class == ec) & (n.aspect_class == ac)).values
            r = {'elev_class': ec, 'aspect': ac, 'n_points': int(m.sum())}
            for c in COLS:
                if c == 'melt_out':
                    for lab, d in (('old', o), ('new', n)):
                        doy = d.melt_out_doy[m].dropna()
                        r[f'{c}_{lab}'] = (pd.Timestamp('2024-10-01') + pd.Timedelta(days=round(doy.median()))).date() \
                            if len(doy) else None
                    dd = (n.melt_out_doy - o.melt_out_doy)[m].dropna()
                    r[f'{c}_change_days_median'] = dd.median() if len(dd) else np.nan
                else:
                    r[f'{c}_old'] = round(o[c][m].median(), 1)
                    r[f'{c}_new'] = round(n[c][m].median(), 1)
                    r[f'{c}_change_median'] = round((n[c] - o[c])[m].median(), 1)
            r['n_old_sector_differs'] = int(n.old_sector_differs[m].sum())
            rows.append(r)
    t = pd.DataFrame(rows)
    t.to_csv(OUT / 'compare_old_new_by_class_aspect.csv', index=False)
    with pd.option_context('display.width', 250, 'display.max_columns', 40):
        print(t.to_string(index=False))

    # SWE / HS old (dashed) vs new (solid), N and S, per elevation class
    do = xr.open_dataset(VARIANTS['old']['out'] / 'daily_hs_swe.nc')
    dn = xr.open_dataset(OUT / 'daily_hs_swe.nc')
    days = pd.DatetimeIndex(dn.day.values)
    fig, ax = plt.subplots(2, 4, figsize=(13, 6), sharex=True, sharey='row', constrained_layout=True)
    for j, ec in enumerate(ELEV_LABELS):
        for ac, col in (('N', C_N), ('S', C_S)):
            m = ((n.elev_class == ec) & (n.aspect_class == ac)).values
            for i, k in enumerate(('SWE', 'HS')):
                ax[i, j].plot(days, do[k].values[:, m].mean(1), color=col, lw=1.2, ls='--', alpha=0.9,
                              label=f'{ac} old')
                ax[i, j].plot(days, dn[k].values[:, m].mean(1), color=col, lw=2, label=f'{ac} new (n={m.sum()})')
        ax[0, j].set_title(f'{ec} m')
        ax[0, j].legend(frameon=False, loc='upper left', fontsize=7.5)
        ax[1, j].xaxis.set_major_formatter(mdates.DateFormatter('%b'))
        ax[1, j].xaxis.set_major_locator(mdates.MonthLocator(bymonth=[10, 12, 2, 4, 6, 8]))
    ax[0, 0].set_ylabel('SWE (mm)')
    ax[1, 0].set_ylabel('Snow depth HS (m)')
    for a in ax.flat:
        a.set_ylim(bottom=0)
    fig.suptitle('Crocus HY 2024-2025: mean SWE and HS by elevation class and terrain aspect, '
                 'old (dashed) vs fixed (solid) TopoPyScale shortwave', color=INK)
    fig.savefig(OUT / 'fig_compare_swe_hs_old_new.png')
    plt.close(fig)

    # per cluster: change of peak SWE vs change of DJF SW
    fig, ax = plt.subplots(figsize=(6.5, 4.5), constrained_layout=True)
    dsw, dswe = n.SW_DJF_Wm2 - o.SW_DJF_Wm2, n.peak_SWE_mm - o.peak_SWE_mm
    moved = n.old_sector_differs.values
    ax.scatter(dsw[~moved], dswe[~moved], s=6, color=C_GREY, alpha=0.5, lw=0, label='same sector old/new')
    ax.scatter(dsw[moved], dswe[moved], s=8, color=C_S, alpha=0.7, lw=0,
               label=f'aspect sector changed by the circular mean (n={moved.sum()})')
    ax.axhline(0, color=INK, lw=0.6)
    ax.axvline(0, color=INK, lw=0.6)
    ax.set_xlabel('Change of DJF mean SW, new - old (W m$^{-2}$)')
    ax.set_ylabel('Change of peak SWE, new - old (mm)')
    ax.legend(frameon=False, fontsize=8)
    ax.set_title('Per cluster, HY 2024-2025', loc='left')
    fig.savefig(OUT / 'fig_compare_dSWE_vs_dSW.png')
    plt.close(fig)


if __name__ == '__main__':
    main()
