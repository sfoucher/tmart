# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**T-Mart** (Topography-adjusted Monte-Carlo Adjacency-effect Radiative Transfer) is a scientific Python package for simulating radiative transfer in 3D surface-atmosphere systems and correcting adjacency effects in aquatic remote sensing. It uses Monte Carlo photon tracing for accurate radiative transfer modeling.

## Installation

```bash
# Recommended (for Py6S and rasterio)
conda create --name tmart python=3.9
conda activate tmart
conda install -c conda-forge Py6S rasterio==1.3.9
pip install tmart

# Or basic install
pip install tmart
```

## Commands

```bash
# Run tests
python -m pytest tests/test_basic.py -v
python -m pytest tests/ -v

# Build documentation (Sphinx)
make html
```

Some tests may download MERRA2 data or require EarthData credentials.

## Architecture

The package has two layers:

**Core RT simulation** (`tmart/`):
- `tmart.py` + `tmart2.py` — `Tmart` class orchestrating photon tracing; multiprocessing via `pathos.ProcessingPool`
- `Surface.py` — `Surface` (DEM + reflectance arrays) and `SpectralSurface` (wavelength-dependent lookup from `ancillary/*.csv`)
- `Atmosphere.py` — Wraps Py6S for layered atmospheric profiles (Rayleigh + aerosol)
- `tm_geometry.py`, `tm_intersect.py`, `tm_water.py` — Ray-triangle intersection, water refraction, Cox-Munk wind roughness

**AEC submodule** (`tmart/AEC/`): High-level pipeline for satellite products (Sentinel-2, Landsat 8/9, PRISMA):
- Detects sensor type → downloads MERRA2 ancillary → water masking → tiles scene → runs T-Mart per tile

## Key Conventions

### Multiprocessing
- **Always wrap `tmart.run()` in `if __name__ == "__main__":`** — required on Windows, recommended everywhere
- Uses `pathos` (not stdlib `multiprocessing`) to support lambda/nested function serialization
- `nc='auto'` uses all available cores; `njobs=100` sets fine-grained job distribution

### Units & Coordinate System
- DEM: meters (2D numpy array)
- Reflectance: 0–1 range (2D numpy array matching DEM shape)
- Wavelength: nanometers (400–2400 nm range)
- Coordinates: `[easting, northing, elevation]` in meters; azimuth in degrees (0°=North, 90°=East)
- `isWater`: 1=water (Cox-Munk refraction), 0=land (Lambertian)
- Spectral CSV files in `ancillary/`: wavelength in µm, value in %

### Py6S Integration
- All atmospheric calculations go through `tmart.Atmosphere`; never call Py6S directly
- Aerosol types: `'Maritime'`, `'Continental'`, `'Desert'`, `'Urban'`, `'BiomassBurning'`, `'Stratospheric'`, or float 0–1 (Maritime/Continental mix)
- Requires 6S binary installed via conda; fails silently if missing

### Configuration
- Runtime config in `tmart/config/config.txt` (water detection thresholds, AEC tile sizes, etc.)
- Key AEC parameters: `reshape_factor` (speed/accuracy), `window_size` (must be odd), `mask_NDWI_threshold`

## Typical Usage Patterns

**Basic simulation:**
```python
import tmart
my_surface = tmart.Surface(DEM=image_DEM, reflectance=image_reflectance,
                           isWater=image_isWater, cell_size=10_000)
my_atm = tmart.Atmosphere(atm_profile, aot550=0.1, aerosol_type='Maritime')
my_tmart = tmart.Tmart(Surface=my_surface, Atmosphere=my_atm)
my_tmart.set_geometry(sensor_coords=[x,y,z], sun_dir=[theta, phi],
                      target_pt_direction=[theta, phi])
results = my_tmart.run(wl=833, n_photon=10_000, nc='auto', njobs=100)
R = tmart.calc_ref(results, detail=True)
```

**Spectral loop** (atmosphere recomputed per wavelength — loop externally):
```python
water_spectrum = tmart.SpectralSurface('water_chl1')
ref_at_550nm = water_spectrum.wl(550)
```

**AEC for satellite products** (~20 min Landsat, ~30 min Sentinel-2 on 8-core):
```python
if __name__ == "__main__":
    tmart.AEC.run(file='path/to/S2.SAFE', username='earthdata_user', password='earthdata_pass')
```

**Debugging** (single core, per-photon logging):
```python
my_tmart.print_on = True
results = my_tmart.run(wl=833, n_photon=100, nc=1)
```

## Common Pitfalls

- T-Mart is CPU-bound only; no GPU acceleration
- Higher `n_photon` reduces noise linearly with runtime (AEC default: 100k; basic: 10k)
- Spectral mode requires an external wavelength loop — there is no built-in multi-wavelength batch run
- `rasterio==1.3.9` pinned version required for AEC geospatial operations
