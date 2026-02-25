import rasterio
from rasterio.transform import Affine
import numpy as np
import os

dem_path = os.getcwd()+ "/Sources/NASADEM/data/NASADEM_DEM_30.tif"

raster = rasterio.open(dem_path)
dem_array = raster.read(1)

print(raster.transform.e)

#calculating the slope using gradient function
slope_x,slope_y = np.gradient(dem_array,raster.transform.a,raster.transform.e)
slope_radians = np.arctan(np.sqrt(slope_x**2,slope_y**2))

#slope to degrees
slope_degrees = np.degrees(slope_radians)

# Copy the source metadata and update data type
meta = raster.meta.copy()
meta.update(dtype=rasterio.float32, count=1)

#write slope data into in a new raster type 

with rasterio.open(os.getcwd()+ "/Sources/NASADEM/data/NASADEM_SLOPE_30.tif", 'w', **meta) as dst:
       dst.write(slope_degrees.astype(rasterio.float32), 1)
       



