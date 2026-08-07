import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path("/app/bulgaria_rila_pirin/data/meterac")
EXPECTED_PER_HOUR = 12  # nominal 5-min reporting for all METER.AC nodes (confirmed via metadata)
COMPLETE_MIN_OBS = 10   # >=10/12 -> complete (allow 1-2 dropped readings)

STATIONS = [
    "N27", "N32", "N48", "N058", "N067", "N072", "N081", "N094", "N096",
    "N097", "N098", "N108", "N110", "N122", "N141", "N142", "N155", "N164",
    "N175", "N221", "N235", "N303", "N306", "N313", "N321", "N323", "N330", "N349",
]


def classify(n):
    if n == 0:
        return "gap"
    elif n < COMPLETE_MIN_OBS:
        return "partial"
    else:
        return "complete"


all_hourly = []
station_summaries = []

for node in STATIONS:
    raw_path = DATA_DIR / f"{node}_history_raw.txt"
    raw = pd.read_csv(raw_path, usecols=["T [deg C]", "Unix time"])
    raw = raw.rename(columns={"T [deg C]": "temp_c", "Unix time": "unix_time"})
    raw["temp_c"] = pd.to_numeric(raw["temp_c"], errors="coerce")
    raw["dt"] = pd.to_datetime(raw["unix_time"], unit="s", utc=True)
    raw = raw.dropna(subset=["dt"]).sort_values("dt")

    hourly = raw.set_index("dt")["temp_c"].resample("1h").agg(["min", "max", "mean", "count"])
    hourly = hourly.rename(columns={"min": "temp_c_min", "max": "temp_c_max", "mean": "temp_c_mean", "count": "n_obs"})

    full_range = pd.date_range(hourly.index.min(), hourly.index.max(), freq="1h", tz="UTC")
    hourly = hourly.reindex(full_range)
    hourly["n_obs"] = hourly["n_obs"].fillna(0).astype(int)
    hourly.index.name = "time_utc"
    hourly["coverage"] = hourly["n_obs"].apply(classify)
    hourly.insert(0, "node", node)

    out_path = DATA_DIR / f"{node}_hourly_full_history.csv"
    hourly.to_csv(out_path)
    all_hourly.append(hourly)

    n_total = len(hourly)
    n_complete = int((hourly.coverage == "complete").sum())
    n_partial = int((hourly.coverage == "partial").sum())
    n_gap = int((hourly.coverage == "gap").sum())
    station_summaries.append({
        "node": node,
        "start": hourly.index.min(),
        "end": hourly.index.max(),
        "n_hours_total": n_total,
        "pct_complete": round(100 * n_complete / n_total, 1),
        "pct_partial": round(100 * n_partial / n_total, 1),
        "pct_gap": round(100 * n_gap / n_total, 1),
    })
    print(f"{node}: {n_total} hours [{hourly.index.min().date()} -> {hourly.index.max().date()}], "
          f"{n_complete} complete / {n_partial} partial / {n_gap} gap")

combined = pd.concat(all_hourly)
combined.to_csv(DATA_DIR / "all_stations_hourly_full_history.csv")
print(f"\nWrote combined file: {DATA_DIR / 'all_stations_hourly_full_history.csv'} ({len(combined)} rows)")

summary_df = pd.DataFrame(station_summaries).sort_values("start")
summary_df.to_csv(DATA_DIR / "station_coverage_summary.csv", index=False)
pd.set_option("display.width", 160)
print("\nPer-station summary (sorted by start):")
print(summary_df.to_string(index=False))
