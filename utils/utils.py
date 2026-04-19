from collections import namedtuple
import logging
import os

logger = logging.getLogger(__name__)


def get_collection(year: int) -> str:
    """Return the GEE collection name for the given acquisition year."""
    if year >= 2018:
        return "COPERNICUS/S2_SR_HARMONIZED"
    elif year >= 2013:
        return "LANDSAT/LC08/C02/T1_L2"
    elif year >= 1984:
        return "LANDSAT/LT05/C02/T1_L2"
    raise ValueError(f"Year {year} is not supported (must be >= 1984)")


def check_folder_exists(path: str, last_checkpoint: bool) -> str:
    if not os.path.exists(path): 
        return path
    
    counter = 2
    new_folder_path = f"{path}_v{counter}"
    
    while os.path.exists(new_folder_path):
        counter += 1
        new_folder_path = f"{path}_{counter}"

    if last_checkpoint:
        return path if (counter - 1) == 1 else f"{path}_{counter - 1}"
    return new_folder_path

def init_setup(base_path: str, cfg: namedtuple, last_checkpoint: bool) -> dict:
    """
    Create the output folder tree and return a mapping of save paths to run metadata.

    Folder structure:
        results/<suffix>_<year>_<mode>_target_<id>_tide_<height>/
            s1/, s2A/, s2B/, s3/, <final>/

    Returns:
        dict mapping each save_path → {target_id, tidal_height, year}
    """
    folders_2_create = {
        "s1"   : ["merged_bbox_shapefiles", "merge_bbox_ref_pt"],
        "s2A"   : ["Bbox_section", "best_bbox_ref_date", "tide_height"],
        "s2B"   : ["data", "plot"],
        "s3"   : ["_NODATA", "_NODATAselec", "_vrt",
                  "PCA", "PCA_ACM", "PCA_ACMselecL", "PCA_ACMselecL_bbox", "PCA_ACMselecL_RMbbox", "PCA_ACMselec",
                  "Kmeans", "Kmeans_ACM", "Kmeans_ACMselecL", "Kmeans_ACMselecL_bbox", "Kmeans_ACMselecL_RMbbox", "Kmeans_ACMselec",
                  ],
        "Final": [""],
    }
    
    shores_2_extract = {}
    
    for year in cfg.s0.year:
        save_path = os.path.join(base_path, "results", f"{cfg.s0.suffix}_{year}_{cfg.s0.mode}")
        
        logger.info("[s0] Creating save path: %s", save_path)

        for target_ids in cfg.s0.target_ids:
            save_path_id = f"{save_path}_target_{target_ids}"

            for tidal_height in cfg.s0.target_tidal_height:
                save_path_height = f"{save_path_id}_tide_{tidal_height}"

                save_path_height = check_folder_exists(save_path_height, last_checkpoint)

                shores_2_extract[save_path_height] = {
                    "target_id"     : target_ids,
                    "tidal_height"  : tidal_height,
                    "year"          : year,
                }
                
                for stage_folder in folders_2_create:
                    if stage_folder == "Final":
                        os.makedirs(os.path.join(save_path_height, save_path_height.split("/")[-1]), exist_ok=True)
                    else:
                        for sub_folder in folders_2_create[stage_folder]:
                            os.makedirs(os.path.join(save_path_height, stage_folder, sub_folder), exist_ok=True)
                        
    return shores_2_extract
    