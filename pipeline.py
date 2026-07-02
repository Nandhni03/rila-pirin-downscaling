from TopoPyScale import topoclass as tc
from matplotlib import pyplot as plt

config_file = './config.yml'
mp = tc.Topoclass(config_file)

# Step 1: DEM-derived parameters (slope, aspect, sky-view factor) — no network needed
mp.compute_dem_param()

# Step 2: cluster the DEM (k-means) and extract centroid topo parameters
mp.extract_topo_param()

# Step 3: solar geometry and horizon angles — no network needed
mp.compute_solar_geometry()
mp.compute_horizon()

# Step 4: fetch ERA5 (this is the network-heavy step)
mp.get_era5()

# Step 5: run the actual TopoSCALE downscaling
mp.downscale_climate()

# Step 6: export
mp.to_netcdf()
