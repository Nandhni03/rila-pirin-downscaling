"""
NCAR download progress, one bar per year a lane is working on (13 Nov 2026).
    cd ~/TopoPyScale-repo-github/downscaling && ../venv/bin/python meridionali_zarr/scripts/ncar_progress.py
Counts units 'written' in each year's NCAR store manifest against the year's total (from the downloader log line
'N units in selection'); rate = units written in the last 10 min; data = bytes received by this PC (eth0) since the
first call (state in data/logs/overnight_E/ncar_progress_state.json).
"""
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

MZ = Path(__file__).resolve().parents[1]
STORE = MZ / 'data' / 'era5_600-1000hPa_ncar'
LOGS = MZ / 'data' / 'logs' / 'overnight_E'
STATE = LOGS / 'ncar_progress_state.json'


def bar(p, w=30):
    n = int(round(p * w))
    return '█' * n + '░' * (w - n)


def rx_bytes():
    for line in Path('/proc/net/dev').read_text().splitlines():
        if line.strip().startswith('eth0:'):
            return int(line.split(':')[1].split()[0])
    return 0


now = datetime.now()
st = json.loads(STATE.read_text()) if STATE.exists() else {}
if 'rx0' not in st:
    st = {'rx0': rx_bytes(), 't0': now.isoformat()}
    STATE.write_text(json.dumps(st))
active = {}
for lane in ('ncar1', 'ncar2', 'ncar3'):                 # newest lane output (hotspot 13 Nov, wired from 15 Nov)
    outs = sorted(LOGS.glob(f'{lane}_*.out'), key=lambda f: f.stat().st_mtime)
    if outs:
        ys = re.findall(r'\*\*(\d{4}) ERA5 NCAR\*\*', outs[-1].read_text())
        if ys:
            active[lane] = ys[-1]
print(f'{now:%H:%M}  NCAR, counter since {st["t0"][11:16]}; data received {(rx_bytes() - st["rx0"]) / 1e9:.2f} GB')
for lane, y in sorted(active.items()):
    man = STORE / y / 'state' / 'manifest.jsonl'
    rows = [json.loads(l) for l in man.read_text().splitlines() if l.strip()] if man.exists() else []
    w = [r for r in rows if r.get('status') == 'written']
    recent = sum(1 for r in w if r.get('logged') and datetime.fromisoformat(r['logged']) > now - timedelta(minutes=10))
    total = None
    for lg in sorted(LOGS.glob(f'era5_{y}_ncar_{lane}_*.log')) + sorted((STORE / y / 'logs').glob('*.log')):
        m = re.findall(r'(\d+) units in selection', lg.read_text(errors='replace'))
        if m:
            total = int(m[-1])
    total = total or 2274
    left = total - len(w)
    eta = f', ~{left / (recent / 10) / 60:.1f} h left' if recent else ''
    print(f'{lane} {y}  {bar(len(w) / total)} {len(w):4d}/{total} ({100 * len(w) / total:4.1f} %)  '
          f'{recent * 6} units/h{eta}')
