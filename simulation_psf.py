import tmart
import os, sys
import mgrs
import Py6S, math
import numpy as np
import pandas as pd
from tqdm import tqdm
from datetime import datetime

import matplotlib.pyplot as plt

metadata = {}

metadata['AEC_bands_name'] = ['B01','B02','B03','B04','B05','B06','B07','B08','B8A','B11','B12']
metadata['AEC_bands_6S'] = [Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_01),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_02),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_03),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_04),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_05),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_06),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_07),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_08),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_8A),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_11),
                            Py6S.Wavelength(Py6S.PredefinedWavelengths.S2A_MSI_12)]
metadata['AEC_bands_wl'] = [442.7, 492.7, 559.8, 664.6, 704.1, 740.5, 782.8, 832.8, 864.7, 1613.7, 2202.4]

# Reshape_factor
# In AEC, cell_size is tm_sensor_res * reshape_factor
# It has to be divisible by image resolution of all bands for now 
# Larger value: faster processing, lower accuracy and creating pixel artifacts on the output image
# S2 options: 2, 6, 12, 18, 24; L8 options: any

reshape_factor_S2 = 6


r_maritime= 0.2948624081152167
Angstrom_exp= 1.321070544948702
SSA= 0.9325107736124753
AOT_MERRA2= 0.13602766697928173

tm_pt_dir= [176.6, 220.34]
tm_sun_dir= [27.28, 56.89]

water_vapour= 30.628286213027657  # in g/cm2
ozone= 318.3913675590623          # in DU
atm_profile= {'water_vapour': water_vapour, 'ozone': ozone}

SR= 0.125
n_photon= 100_000
njobs= 100
aot550 =0.13602766697928173
window_size= 201
sensor_resolution = {'B01': 60, 'B02': 10, 'B03': 10, 'B04': 10, 'B05': 20, 'B06': 20, 'B07': 20, 'B08': 10, 'B8A': 20,'B09': 60,'B10': 60, 'B11': 20, 'B12': 20}
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
records= []
for r_maritime in tqdm([0.25,0.5,0.75], desc="r_maritime"):
    for sun_zenith_angle in tqdm(range(20,65,2), desc="Sun zenith angle", leave=False):
        tm_sun_dir= [float(sun_zenith_angle), 56.89]
        for water_vapour in tqdm([10.0,20.0,30.0,40.0], desc="WV", leave=False):
            atm_profile= {'water_vapour': water_vapour, 'ozone': ozone}
            for aot550 in tqdm([0.05, 0.1, 0.2, 0.4, 0.5], desc="AOT550", leave=False):
                # AEC for each of the specified bands 
                for i in tqdm([1, 2, 3, 7], desc="Bands", leave=False):#range(len(metadata['AEC_bands_name'])):
                    AEC_band_name = metadata['AEC_bands_name'][i] 
                    AEC_band_6S = metadata['AEC_bands_6S'][i]
                    # Number of cells in AEC along each axis 
                    # larger value: slower processing, less violation of assuming all diffuse radiation comes from the window
                    # must be an odd number
                    res_AEC = int(sensor_resolution[AEC_band_name] * reshape_factor_S2)

                    # Calculate distance map (distance from center in meters)
                    conv_window_1= np.ones((window_size, window_size))
                    y_ind, x_ind = np.indices(conv_window_1.shape)
                    center_y, center_x = int(conv_window_1.shape[0] / 2), int(conv_window_1.shape[1] / 2)
                    distance_map = np.sqrt(((y_ind - center_y) * res_AEC)**2 + ((x_ind - center_x) * res_AEC)**2).astype(np.int32)

                    wl = metadata['AEC_bands_wl'][i]
                    print('\n============= AEC: {} ==================='.format(AEC_band_name))
                    #tmart.AEC.AEC(AEC_band_name, AEC_band_6S, wl, AOT, metadata, config, anci, mask_cloud, mask_all, n_photon, njobs)
                    # Calculate AEC parameters 
                    AEC_parameters = tmart.AEC.get_parameters(n_photon = n_photon, SR = SR, wl = wl, band = AEC_band_6S, 
                                                            target_pt_direction=tm_pt_dir, sun_dir=tm_sun_dir, 
                                                            atm_profile = atm_profile, 
                                                            aerosol_type = r_maritime, aot550 = aot550, 
                                                            cell_size = res_AEC,
                                                            window_size = window_size, isWater = 0, njobs=njobs)
                    
                    conv_window_1   = AEC_parameters['conv_window_1']
                    F_correction    = AEC_parameters['F_correction']
                    F_captured      = AEC_parameters['F_captured']
                    R_atm           = AEC_parameters['R_atm']

                    # Compute the average value of conv_window_1 according to each value in distance_map
                    unique_distances = np.unique(distance_map)
                    avg_conv_values = np.array([conv_window_1[distance_map == d].mean() for d in unique_distances])
                    temp= (distance_map == 10)
                    # Interpolate values for 10 distance values between the min and max of unique_distances
                    target_distances = np.linspace(unique_distances.min(), unique_distances.max(), 10)
                    target_distances = np.array([0, 1, 2, 4, 8, 16, 32, 64, 100])*res_AEC
                    interpolated_values = np.interp(target_distances, unique_distances, avg_conv_values)
                    #print(f"Interpolated values for {AEC_band_name}: {interpolated_values}")
                    record= [wl, *tm_pt_dir, *tm_sun_dir, r_maritime, aot550, water_vapour, ozone, float(F_correction), float(F_captured), float(R_atm), *interpolated_values.tolist()]
                    records.append(record)

                    #plt.plot(unique_distances, avg_conv_values, label=AEC_band_name)
            columns = ['wl', 'tm_pt_dir0', 'tm_pt_dir1', 'tm_sun_dir0', 'tm_sun_dir1', 'r_maritime', 'aot550', 'water_vapour', 'ozone', 'F_correction', 'F_captured', 'R_atm', 
                    'psf0', 'psf1', 'psf2', 'psf4', 'psf8', 'psf16', 'psf32', 'psf64', 'psf100']
            
            # Action: make this a numpy array to speed up computation 
            df = pd.DataFrame(records, columns = columns, index=None)
            
            df.to_csv(f'./tmart/data/simulations-{n_photon}-{res_AEC}_{timestamp}.csv')
#plt.xlabel('Distance (m)')
#plt.ylabel('Average Convolution Value')
#plt.legend()
#plt.show()