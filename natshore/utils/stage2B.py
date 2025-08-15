from datetime import datetime, timedelta

import geedim as gd ; gd.Initialize()
import os

def s2B_geedim_download(
                       save_folder: str,
                       bbox_idx: str,
                       year: int,
                       target_id: str,
                    #    Geedim_collection: str,
                       ):
    if year >= 2018:
        Geedim_collection = "COPERNICUS/S2_SR_HARMONIZED"
    elif year >= 2013:
        Geedim_collection = "LANDSAT/LC08/C02/T1_L2"
    elif year >= 1984:
        Geedim_collection = "LANDSAT/LT05/C02/T1_L2"
    else:
        raise ValueError("Year must be >= 1984 for Landsat or >= 2018 for Sentinel-2")

    bbox = open(f"{save_folder}/s2A/best_bbox_ref_date/{bbox_idx}.txt", "r").readlines()[1:][0].replace("(", "").replace(")", "").strip().split(", ")

    x1, y1, x2, y2, ref_ptx, ref_pty, best_date, best_height, best_fill, best_cloudless, order = bbox

    x1 = float(x1) ; y1 = float(y1) ; x2 = float(x2) ; y2 = float(y2)
    ref_ptx = float(ref_ptx) ; ref_pty = float(ref_pty)

    best_date = datetime.strptime(best_date, "%Y-%m-%d %H:%M:%S")
    best_date = best_date.strftime("%Y-%m-%d-%H-%M-%S")
    best_height = float(best_height)
    
    TARGET_DATE        = best_date[0:10] # "2021-02-20-01-57-12" - > "2021-02-20"
    TARGET_DATEplus1   = (datetime.strptime(TARGET_DATE, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        
    bbox = [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]
    
    sensor, projection, crss = "S2H", 'Mercator','EPSG:3395'    
    Geedim_outimg_path_parent = f"{save_folder}/s2B/data/"
    out_name           = str(bbox_idx) + "__" + sensor + "_geedim_" + TARGET_DATE + "_" + projection
    if os.path.exists(Geedim_outimg_path_parent + out_name + ".tif"):
        # print(f"Skipping {bbox_idx} as it already exists")
        return
    
    if Geedim_collection == "COPERNICUS/S2_SR" or Geedim_collection == "COPERNICUS/S2" or Geedim_collection == "COPERNICUS/S2_SR_HARMONIZED":
        selected_bands = ["B1", "B2", "B3", "B4", "B8", "B11", "B12"]
        
    elif Geedim_collection == "LANDSAT/LC08/C02/T1_L2" or Geedim_collection == "LANDSAT/LC09/C02/T1_L2":
        selected_bands = ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]

    elif Geedim_collection == "LANDSAT/LT05/C02/T1_L2":
        selected_bands = ["SR_B1", "SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B7"]
        
    # print("bbox_idx: ", bbox_idx, "save_folder: ", save_folder, "Geedim_collection: ", Geedim_collection)
    
    GEEresolution = 10.0 # (m) with .0

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