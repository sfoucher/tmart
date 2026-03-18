# T-Mart: AI Coding Agent Instructions

## Project Overview

**T-Mart** (Topography-adjusted Monte-Carlo Adjacency-effect Radiative Transfer) is a scientific Python package for simulating radiative transfer in 3D surface-atmosphere systems and correcting adjacency effects in aquatic remote sensing. It uses Monte Carlo photon tracing for accurate radiative transfer modeling.

## Architecture & Key Components

### Core Modules (in `tmart/`)

1. **`tmart.py` + `tmart2.py`** — Main `Tmart` class orchestrates radiative transfer simulation:
   - Ray tracing against DEM using triangular mesh intersections
   - Photon path tracking through atmosphere and surface interactions
   - Multiprocessing with `pathos.ProcessingPool` for parallel photon tracing
   - Uses `__name__ == "__main__"` guard for Windows compatibility (required for multiprocessing)

2. **`Surface.py`** — Surface definition with DEM, reflectance, water masks:
   - `Surface` class: raster-based geometry with cell size
   - `SpectralSurface` class: wavelength-dependent reflectance from CSV lookup tables
   - Data stored in `ancillary/` (soil.csv, vegetation.csv, water_chl1.csv, etc.)
   - Background surface setup via `set_background()` for heterogeneous environments

3. **`Atmosphere.py`** — Wavelength-dependent atmosphere layers:
   - Wraps Py6S for 6S radiative transfer calculations
   - Creates layered atmosphere profile with Rayleigh & aerosol scattering
   - Integrates with aerosol types (Maritime, Continental, Desert, etc.)

4. **`tm_geometry.py`, `tm_intersect.py`, `tm_water.py`** — Ray tracing utilities:
   - Ray-triangle intersection for DEM collision detection
- Water refraction and Fresnel reflectance (Cox-Munk for wind roughness)

### AEC (Adjacency-Effect Correction) Submodule

High-level workflow in `tmart/AEC/`:
- **`run.py`** — Main entry point; orchestrates full AEC pipeline
- **`identify_input.py`** — Sensor detection (Sentinel-2, Landsat 8/9, PRISMA)
- **`get_ancillary.py`** — AOT, water vapor from MERRA2/EarthData
- **`run_regular.py` / `run_acoliteL1R.py`** — Sensor-specific processing
- Multiprocessing jobs distributed across tiles; progress tracked via job counter

## Critical Developer Workflows

### Running Tests
Tests in `tests/test_*.py` follow pytest convention but require `if __name__ == "__main__":` wrapping for multiprocessing:
```bash
cd /home/sfoucher/DEV/tmart
python -m pytest tests/test_basic.py -v
```
Note: Some tests may download MERRA2 data or require EarthData credentials.

### Running Basic Simulation
```python
import tmart
from Py6S.Params.atmosprofile import AtmosProfile

# 1. Define surface (DEM in meters, reflectance 0-1, water mask)
my_surface = tmart.Surface(DEM=image_DEM, reflectance=image_reflectance, 
                           isWater=image_isWater, cell_size=10_000)

# 2. Define atmosphere (from Py6S profile)
atm_profile = AtmosProfile.PredefinedType(AtmosProfile.MidlatitudeSummer)
my_atm = tmart.Atmosphere(atm_profile, aot550=0.1, aerosol_type='Maritime')

# 3. Setup geometry and run
my_tmart = tmart.Tmart(Surface=my_surface, Atmosphere=my_atm)
my_tmart.set_geometry(sensor_coords=[x,y,z], sun_dir=[theta, phi], 
                      target_pt_direction=[theta, phi])
results = my_tmart.run(wl=833, n_photon=10_000, nc='auto', njobs=100)

# 4. Calculate reflectance from photon traces
R = tmart.calc_ref(results, detail=True)
```

### Running Adjacency-Effect Correction
```python
import tmart
if __name__ == "__main__":
    tmart.AEC.run(file='path/to/S2_or_L8_product', 
                  username='earthdata_user', 
                  password='earthdata_pass',
                  n_photon=100_000)  # Typical: ~20min L8, ~30min S2
```

## Project-Specific Conventions

### Multiprocessing Rules
- **Always wrap `tmart.run()` calls in `if __name__ == "__main__":`** — Required for Windows; optional but recommended for Unix
- Multiprocessing uses `pathos` (not `multiprocessing`), which can serialize lambdas and nested functions
- Default: `nc='auto'` (uses available cores), `njobs=100` (fine-grained job distribution)
- Progress printed as: `Jobs remaining = {count}` every 2 seconds

### Data & Coordinate Systems
- **DEM**: meters above reference, 2D numpy array
- **Reflectance**: 0-1 range, 2D numpy array matching DEM shape
- **Wavelength**: nanometers (nm), typically 400-2400 for remote sensing
- **Coordinates**: [easting, northing, elevation] in meters; azimuth directions in degrees (0°=North, 90°=East)
- **isWater**: 1=water, 0=land; used for refraction (Cox-Munk) vs. Lambertian reflection

### Configuration
- Settings in `tmart/config/config.txt` (editable, read at runtime)
- Spectral lookup tables in `tmart/ancillary/*.csv` (wl in µm, value in %)
- AEC config keys (e.g., `mask_SWIR_threshold`) can override via function arguments

### Py6S Integration
- All atmospheric properties computed via Py6S 6S model
- `Atmosphere` class wraps Py6S internally; users don't call Py6S directly
- Aerosol types: `'Maritime'`, `'Continental'`, `'Desert'`, `'Urban'`, `'BiomassBurning'`, `'Stratospheric'`, or decimal 0-1 (Maritime/Continental mix ratio)

## Integration Points & External Dependencies

| Dependency | Purpose | Notes |
|---|---|---|
| `Py6S` | Atmospheric radiative transfer | Installed via conda; 6S binary required |
| `scipy.interpolate` | Spectral reflectance lookup | Linear interpolation for wavelength-dependent surfaces |
| `rasterio` (v1.3.9) | GeoTIFF reading | Used in AEC for satellite product parsing |
| `netCDF4` | MERRA2 download | Environmental ancillary data |
| `geopandas` | Vector geometry | MGRS tile handling for satellite scenes |
| `pathos` | Serializable multiprocessing | Supports lambda serialization unlike stdlib `multiprocessing` |

## Common Pitfalls & Patterns

1. **GPU not used** — T-Mart is CPU-bound (Monte Carlo photon tracing). Optimization focuses on multiprocessing job distribution.
2. **Windowing issues** — On Windows, *all* multiprocessing code must be in `if __name__ == "__main__"` block, including test runners.
3. **Photon count vs. accuracy** — Higher `n_photon` reduces noise but scales linearly with runtime. AEC typically uses 100k; basic modeling uses 10k.
4. **Spectral mode** — Loop wavelengths externally (see `test_plot.py` for examples); atmosphere recomputed per wavelength.
5. **Large tiles slow** — AEC automatically tiles large scenes; custom tile size set in config.
6. **Py6S path** — Must have 6S binary installed (`conda install -c conda-forge Py6S`); fails silently if missing.

## Code Examples

**Spectral reflectance lookup:**
```python
water_spectrum = tmart.SpectralSurface('water_chl1')
ref_at_550nm = water_spectrum.wl(550)  # Returns reflectance value
```

**Advanced: Custom radiative transfer with debugging:**
```python
my_tmart.set_wind(wind_speed=3, wind_azi_avg=True)
my_tmart.print_on = True  # Enable per-photon logging
results = my_tmart.run(wl=833, n_photon=100, nc=1)  # Single core for debugging
```

**AEC with custom atmosphere info:**
```python
tmart.AEC.run(file='S2_product.SAFE', 
              atm_info_file='tmart_atm_info_2024-01-01.txt')  # Skip ancillary download
```

## References

- Main reference: Wu et al. (2023), *J. Quant. Spectrosc. Radiat. Transfer* — T-Mart methodology
- AEC application: Wu et al. (2024), *Remote Sensing of Environment* — Adjacency-effect correction
- Docs: https://tmart-rtm.github.io
