from datetime import datetime, timedelta

import geedim as gd ; gd.Initialize()
import logging
import os

from utils.utils import get_collection

logger = logging.getLogger(__name__)


_SENTINEL2_COLLECTIONS = {"COPERNICUS/S2_SR", "COPERNICUS/S2", "COPERNICUS/S2_SR_HARMONIZED"}
_LANDSAT8_9_COLLECTIONS = {"LANDSAT/LC08/C02/T1_L2", "LANDSAT/LC09/C02/T1_L2"}
_LANDSAT5_COLLECTIONS   = {"LANDSAT/LT05/C02/T1_L2"}


def s2B_geedim_download(
                       save_folder: str,
                       bbox_idx: str,
                       year: int,
                       target_id: str,
                       bands_cfg=None,
                       ) -> None:
    """
    Download the best-date satellite composite for a given bounding box via geedim.

    Reads the selected acquisition date from the Stage 2A output, queries the
    appropriate GEE collection, and saves a multi-band GeoTIFF to
    ``save_folder/s2B/data/``.

    Args:
        save_folder: Run-specific output directory for this target/year/tide.
        bbox_idx: Identifier string ``<island_id>_<box_index>``.
        year: Acquisition year (determines GEE collection via :func:`get_collection`).
        target_id: Island/region identifier string.
        bands_cfg: namedtuple from cfg.s2B.bands with fields S2, L8_L9, L5.
    """
    Geedim_collection = get_collection(year)

    with open(f"{save_folder}/s2A/best_bbox_ref_date/{bbox_idx}.txt", "r") as fh:
        bbox = fh.readlines()[1:][0].replace("(", "").replace(")", "").strip().split(", ")

    x1, y1, x2, y2, ref_ptx, ref_pty, best_date, best_height, best_fill, best_cloudless, order = bbox

    x1 = float(x1) ; y1 = float(y1) ; x2 = float(x2) ; y2 = float(y2)
    ref_ptx = float(ref_ptx) ; ref_pty = float(ref_pty)

    best_date = datetime.strptime(best_date, "%Y-%m-%d %H:%M:%S")
    best_date = best_date.strftime("%Y-%m-%d-%H-%M-%S")
    best_height = float(best_height)
    
    TARGET_DATE        = best_date[0:10] # "2021-02-20-01-57-12" - > "2021-02-20"
    TARGET_DATEplus1   = (datetime.strptime(TARGET_DATE, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        
    bbox = [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]
    
    sensor, projection, crss = "S2H", "Mercator", "EPSG:3395"
    Geedim_outimg_path_parent = f"{save_folder}/s2B/data/"
    out_name = f"{bbox_idx}__{sensor}_geedim_{TARGET_DATE}_{projection}"
    if os.path.exists(Geedim_outimg_path_parent + out_name + ".tif"):
        logger.info("Skipping %s — already downloaded", bbox_idx)
        return
    
    if Geedim_collection in _SENTINEL2_COLLECTIONS:
        selected_bands = list(bands_cfg.S2) if bands_cfg else ["B1", "B2", "B3", "B4", "B8", "B11", "B12"]
    elif Geedim_collection in _LANDSAT8_9_COLLECTIONS:
        selected_bands = list(bands_cfg.L8_L9) if bands_cfg else ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]
    elif Geedim_collection in _LANDSAT5_COLLECTIONS:
        selected_bands = list(bands_cfg.L5) if bands_cfg else ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"]
        
    GEEresolution = 10.0  # metres; Sentinel-2 native resolution

    region             = {"type": "Polygon","coordinates": [bbox]}
    gd_collection      = gd.MaskedCollection.from_name(Geedim_collection)
    gd_collection_fil  = gd_collection.search(TARGET_DATE, TARGET_DATEplus1, region)
    q_mosaic_im        = gd_collection_fil.composite(method = gd.CompositeMethod.q_mosaic, mask = False) # no CLOUD mask!
    
    q_mosaic_im.download(Geedim_outimg_path_parent + out_name + ".tif", 
                        crs        = crss,
                        resampling = "near",
                        region     = region,
                        overwrite  = True,
                        scale      = GEEresolution,
                        dtype      = "uint16",
                        bands      = selected_bands
                        )