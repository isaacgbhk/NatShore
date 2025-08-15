from collections import namedtuple
import os
import sys

class HiddenPrints:
    """
    usage:
    with HiddenPrints():
        print("This will not be printed")
    """
    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout
        
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

def init_setup(base_path: str, cfg: namedtuple, last_checkpoint: bool) -> str:
    """
    Create the save folder structure:
    > suffix_year_mode
        > target_ids
            > tide_height
                > stage_folder
                    > sub_folder
                    
    Returns:
    shores_2_extract: dict
        A dictionary with the save path as the key and the target_ids, tidal_height, and year as the values.
    """
    
    # folders_2_create = {
    #     "s1"   : ["shoreline_Bbox_plot", "section", "merged_section", "merged_bbox", "merged_bbox_txt", "merged_bbox_shapefiles", "merge_bbox_ref_pt"],
    #     "s2A"   : ["Bbox_section", "best_bbox_ref_date", "tide_height"],
    #     "s2B"   : ["data"],
    #     "s3"   : ["output"],
    #     "log"  : [""],
    #     "Final": [""], # Shapefiles for the Qgis/ ArcGIS
    # }

    folders_2_create = {
        "s1"   : ["merged_bbox_shapefiles", "merge_bbox_ref_pt"],
        "s2A"   : ["Bbox_section", "best_bbox_ref_date", "tide_height"],
        "s2B"   : ["data", "plot"],
        "s3"   : ["_NODATA", "_NODATAselec", "_vrt", 
                  "PCA", "PCA_ACM", "PCA_ACMselecL", "PCA_ACMselecL_bbox", "PCA_ACMselecL_RMbbox", "PCA_ACMselec",
                  "Kmeans", "Kmeans_ACM", "Kmeans_ACMselecL", "Kmeans_ACMselecL_bbox", "Kmeans_ACMselecL_RMbbox", "Kmeans_ACMselec"
                  ],
        # "log"  : ["best_tidal_date/out", "download_data/out", "extract_shore/out", "best_tidal_date/err", "download_data/err", "extract_shore/err"],
        "Final": [""], # Shapefiles for the Qgis/ ArcGIS
    }
    
    shores_2_extract = {}
    
    for year in cfg.s0.year:
        save_path = os.path.join(base_path, "results", f"{cfg.s0.suffix}_{year}_{cfg.s0.mode}")
        
        print(f"[s0] Creating save path: {save_path}")

        for target_ids in cfg.s0.target_ids:
            # save_path_id = os.path.join(save_path, f"target_{target_ids}")
            save_path_id = f"{save_path}_target_{target_ids}"

            for tidal_height in cfg.s0.target_tidal_height:

                # save_path_height = os.path.join(save_path_id, f"tide_{tidal_height}")
                save_path_height = f"{save_path_id}_tide_{tidal_height}"

                save_path_height = check_folder_exists(save_path_height, last_checkpoint)

                shores_2_extract[save_path_height] = {
                    "target_id"     : target_ids,
                    "tidal_height"  : tidal_height,
                    "year"          : year,
                }
                
                for stage_folder in folders_2_create.keys():
                    if stage_folder  == "Final":
                        # os.makedirs(os.path.join(save_path_height, f"{cfg.s0.suffix}_{target_ids}_{year}_tide_{tidal_height}"), exist_ok = True)
                        os.makedirs(os.path.join(save_path_height, save_path_height.split("/")[-1]), exist_ok = True)
                    else:    
                        for sub_folder in folders_2_create[stage_folder]:
                            os.makedirs(os.path.join(save_path_height, stage_folder, sub_folder), exist_ok = True)    
                        
    print()                    
    return shores_2_extract
    