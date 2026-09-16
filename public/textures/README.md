# Earth texture and station sources

## Earth texture

`earth-day.jpg` is the original 2048 × 1024 cloud-free JPEG from
[NASA SVS visualization 3615](https://svs.gsfc.nasa.gov/3615/), published in 2009.
[Original file](https://svs.gsfc.nasa.gov/vis/a000000/a003600/a003615/earth_noClouds.0330.jpg).
The file is 356,467 bytes (348 KiB), with no resizing or color changes.
It is served locally; no runtime request to NASA is required.

Credit: NASA/Goddard Space Flight Center Scientific Visualization Studio.
Underlying Blue Marble Next Generation data: Reto Stockli (NASA/GSFC) and NASA
Earth Observatory. This satellite-image composite is not current imagery.

NASA-generated media are generally not subject to copyright in the United
States and may be used for informational websites with attribution under the
[NASA Images and Media Usage Guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/).
The source lists NASA/GSFC credits and no separate third-party restriction for
this image. NASA and KSAT do not endorse this website.

Projection is equirectangular: north at the top, longitude −180° at the left,
+180° at the right, Greenwich at horizontal center, equator at vertical center.
Use it as a color texture with sRGB color space. Align the globe's texture
orientation with the geographic marker coordinate convention.

## KSAT markers

Coordinates below are latitude followed by longitude; east is positive.

| Marker | Latitude | Longitude | Source |
| --- | ---: | ---: | --- |
| Svalbard / SvalSat | 78.2306 | 15.3894 | [USGS Landsat SGS station entry](https://landsat.usgs.gov/SGS) |
| Tromsø | 69.66 | 18.95 | [Brahe's KSAT dataset documentation](https://docs.brahe.space/latest/learn/datasets/groundstations.html) |
| Troll / TrollSat | −72.00215 | 2.525012 | [NASA Near Earth Network Users' Guide, Revision 5](https://ntrs.nasa.gov/api/citations/20205005784/downloads/453NENUGRev5__clean_final_82420.pdf), TR3 antenna entry |

These are approximate site markers on a spherical visual globe, not surveyed
antenna coordinates for orbit operations. Tromsø is rounded to two decimals.
The NASA guide lists multiple Troll antennas with differing longitudes; this
illustration uses the TR3 entry. Satellite trajectories, animation timing,
contact allocations, and single-contact station capacities are illustrative.
They do not reproduce KSAT's operational network or the paper's experiments.

Sources checked September 15, 2026.
