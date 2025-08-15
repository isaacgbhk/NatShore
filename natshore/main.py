from glob import glob
from tqdm import tqdm

import matplotlib.pyplot as plt
import multiprocessing
import os 
import sys
# os.environ['PROJ_LIB']=r'/home/isaac/miniconda3/envs/natshore/lib/python3.10/site-packages/pyproj/proj_dir/share/proj'
# print(os.environ['PROJ_LIB'])

from configs.config import convert
from utils.stage1 import s1_auto_bbox_merge, s1_predefined_bbox_merge
from utils.stage2A import s2A_best_tide_date
from utils.stage2B import s2B_geedim_download
from utils.stage3 import s3_extract_shoreline
from utils.utils import init_setup

def main(args):
    
    last_checkpoint = False
    run_stage1N2A = False
    run_stage2B = False
    run_stage3 = False
    
    last_checkpoint = True
    # run_stage1N2A = True
    # run_stage2B = True
    run_stage3 = True

    # region all stages
    # region Stage 0: Setup
    base_path    = os.path.dirname(__file__)
    config_path  = os.path.join(base_path, "configs", args.config) # "auto_bbox_config.yaml"

    cfg = convert(config_path) # namedtuple
    cfg = cfg._replace(base_path = base_path)

    if cfg.s0.mode == "defined_bbox_wo_ref":
        run_stage1N2A = False
        run_stage2B = True
        run_stage3 = True

    shores_2_extract = init_setup(base_path, cfg, last_checkpoint)

    for k in shores_2_extract.keys():
        print(k, shores_2_extract[k])
        cfg_save_path = "/".join(list(k.split("/")))
        os.system(f"cp {config_path} {cfg_save_path}")
        
    river_folders = sorted(glob(os.path.join(base_path, "data", cfg.s0.river_folders, "*")))
    shore_folders = sorted(glob(os.path.join(base_path, "data", cfg.s0.shore_folders, "*")))
    # endregion 
    
    # region Stage 1: Auto BBox Merge
    if run_stage1N2A:
        print("#" * 100 + "\n" + 
            "Stage 1: Auto Bounding Box".center(100) + 
            f"\nUsing the following parameters: \n"+
            f"Area Threshold (min & max) : {cfg.s1.min_area_th_degree}, {cfg.s1.max_area_th_degree}\n" +
            f"Edge Threshold (min & max) : {cfg.s1.min_edge_th_km}, {cfg.s1.max_edge_th_km}\n" +
            f"BBox Expand                : {cfg.s1.bbox_expand}\n" +
            f"Shore n segments           : {cfg.s1.shore_n_segments}\n" +
            f"Min Distance Threshold     : {cfg.s1.min_dist_th}\n" +
            f"IoU Threshold              : {cfg.s1.iou_th}\n" )

        tides_height_all = {}
        
        for save_folder, info in shores_2_extract.items():
            target_id, tidal_height, year = info["target_id"], info["tidal_height"], info["year"]

            if cfg.s0.mode == "auto_bbox":
                print(f"  * Processing {save_folder.split('/')[-3:]}")

                year_range = cfg.s0.year_range
                
                river_data_path = river_folders[0].split("id_")[0] + f"id_{target_id}"
                shore_data_path = shore_folders[0].split("id_")[0] + f"id_{target_id}"
                
                tides_height_all, s1_results = s1_auto_bbox_merge(river_data_path, shore_data_path, save_folder, base_path, year, year_range,
                                                                  min_area_th_degree = cfg.s1.min_area_th_degree, min_edge_th_km = cfg.s1.min_edge_th_km,
                                                                  max_area_th_degree = cfg.s1.max_area_th_degree, max_edge_th_km = cfg.s1.max_edge_th_km,
                                                                  bbox_expand = cfg.s1.bbox_expand, shore_expand = cfg.s1.shore_expand, shore_n_segments = cfg.s1.shore_n_segments,
                                                                  min_dist_th = cfg.s1.min_dist_th, iou_th = cfg.s1.iou_th,
                                                                  tides_height_all = tides_height_all,
                                                                  target_id = target_id
                                                                  )
            
            elif cfg.s0.mode == "defined_bbox":
                print("defined_bbox !!!!")
                print(f"  * Processing {save_folder.split('/')[-3:]}")
                year_range = cfg.s0.year_range
                tides_height_all, s1_results = s1_predefined_bbox_merge(save_folder, base_path, year, year_range, tides_height_all, target_id)

                # target_id, tidal_height, year = info["target_id"], info["tidal_height"], info["year"]
                # print(f"  * Processing {save_folder.split('/')[-3:]}")

            elif cfg.s0.mode == "defined_bbox_wo_ref":
                predefined_bbox_txt = sorted(glob(f"{save_folder}/s1/merge_bbox_ref_pt/*.txt")) 

                s1_results = {"bbox_id"             : [txt_path.split("/")[-1].split(".")[0] for txt_path in predefined_bbox_txt], 
                              "ref_pt_idx"          : [i for i in range(len(predefined_bbox_txt))], 
                              "ref_pt_dist"         : [0.0 for _ in range(len(predefined_bbox_txt))], 
                              "tide_stats_df_valid" : [],
                              }
                
            shores_2_extract[save_folder]["s1_results"] = s1_results
            plt.close("all")
                
        del tides_height_all
    # endregion

    # region Stage 2: Best Date & Tidal Height
    print("#" * 100 + "\n" + 
            "Stage 2A: Best Date & Tidal Height".center(100) + 
            f"\nUsing the following parameters: \n"+
            f"Target tidal height(s) : {cfg.s0.target_tidal_height}\n" +
            f"Year                   : {cfg.s0.year}\n" +
            "\n" + "- " * 50 + "\n")

    one_by_one = False
    # one_by_one = True

    # region Stage 2A: Best Date & Tidal Height
    if run_stage1N2A:
        for save_folder, info in shores_2_extract.items():
            target_id, tidal_height, year = info["target_id"], info["tidal_height"], info["year"]
            print(f"  * Processing {save_folder.split('/')[-3:]}")
            
            s1_results = shores_2_extract[save_folder]["s1_results"]
            # s2A_best_tide_date
            bbox_idxs = s1_results["bbox_id"]#[15:17]

            if "Banda_Aceh" in save_folder:
                print("!!!!!!!!!!!!!!!!!")
                print("!!!!!!!!!!!!!!!!!")
                print("!!!!!!!!!!!!!!!!!")
                print("Using self-defined points for Banda_Aceh @ Indonesia")
                bbox_idxs = ["12_28"] # For Banda_Aceh @ Indonesia
            
            tide_all = list(s1_results["tide_stats_df_valid"]["tide"])
            tides = [tide_all[i] for i in s1_results["ref_pt_idx"]] ; del tide_all

            year_range = cfg.s0.year_range
            
            if one_by_one:
                for idx, (bbox_idx, tide) in enumerate(zip(bbox_idxs, tides)):
                        print(f"Task {idx} started")
                        s2A_best_tide_date(bbox_idx, base_path, save_folder, 
                                            year, 
                                            year_range,
                                            tide, 
                                            cfg.s2A.cloudless_portion, 
                                            cfg.s2A.fill_portion, 
                                            tidal_height, 
                                            # cfg.s0.Geedim_collection,
                                            mode = cfg.s0.mode,
                                            disable_print = False)
                        print(f"Task {idx} completed")
                        
                        # try:
                        #     print(f"Task {idx} started")
                        #     s2A_best_tide_date(bbox_idx, base_path, save_folder, 
                        #                         year, 
                        #                         year_range,
                        #                         tide, 
                        #                         cfg.s2.cloudless_portion, 
                        #                         cfg.s2.fill_portion, 
                        #                         tidal_height, 
                        #                         cfg.s0.Geedim_collection,
                        #                         disable_print = False)
                        #     print(f"Task {idx} completed")
                        # except Exception as e:
                        #     print(f"Task {idx} failed with error: {e}")
                        #     continue

                #       break
                # break
            
            else: 
                inputs = []
                for idx, (bbox_idx, tide) in enumerate(zip(bbox_idxs, tides)):
                    inputs.append((bbox_idx, base_path, save_folder, year, year_range, 
                                   tide, cfg.s2A.cloudless_portion, cfg.s2A.fill_portion, tidal_height, 
                                #    cfg.s0.Geedim_collection, 
                                   cfg.s0.mode,
                                   True
                                   ))
                    
                with multiprocessing.Pool(processes=min(os.cpu_count(), len(bbox_idxs), 5)) as pool:
                    results = pool.starmap(s2A_best_tide_date, tqdm(inputs, total=len(inputs)))
                    
                if len(bbox_idxs) > 0:
                    pool.close(); pool.join()

            print(f"  * Completed {save_folder.split('/')[-3:]}" + "\n" + "- " * 50 + "\n")
            
    # endregion

    # region Stage 2B: Download Best Date & Tidal Height Data
    
    print("#" * 100 + "\n" + 
      "Stage 2B: Download Data with Best Tidal Height".center(100) + 
      f"\nUsing the following parameters: \n"+
    #   f"Geedim_collection : {cfg.s0.Geedim_collection}\n" +
      f"Year              : {cfg.s0.year}\n" +
      "\n" + "- " * 50 + "\n")

    one_by_one = False
    # one_by_one = True

    if run_stage2B:
        for save_folder, info in shores_2_extract.items():
            target_id, tidal_height, year = info["target_id"], info["tidal_height"], info["year"]
            
            bbox_idxs = glob(f"{save_folder}/s2A/best_bbox_ref_date/*.txt")
            bbox_idxs = sorted([bbox_idx.split("/")[-1].split(".")[0] for bbox_idx in bbox_idxs], key=lambda x: int(x.split("_")[-1]))
            
            print(bbox_idxs)
            if one_by_one:
                for idx, bbox_idx in enumerate(bbox_idxs):
                        s2B_geedim_download(save_folder, 
                                        bbox_idx,
                                        year, 
                                        target_id,
                                        # cfg.s0.Geedim_collection,
                                        )
            else:
                sucess = 0
                while sucess < len(bbox_idxs):
                    sucess = len(glob(f"{save_folder}/s2B/data/*.tif"))
                    print(f"Sucess: {sucess}/{len(bbox_idxs)}")
                    
                    inputs = []
                    for idx, bbox_idx in enumerate(bbox_idxs):
                        inputs.append((save_folder, bbox_idx, year, target_id, 
                                    #    cfg.s0.Geedim_collection
                                       ))
                        
                    with multiprocessing.Pool(min(os.cpu_count(), len(bbox_idxs), 5)) as pool:      
                        pool.starmap(s2B_geedim_download, tqdm(inputs, total=len(inputs)))
                        
                if len(bbox_idxs) > 0:
                    pool.close(); pool.join()
    
    # endregion
    
    # endregion
    
    # region Stage 3: Extract Shoreline
    one_by_one = False
    one_by_one = True

    print("#" * 100 + "\n" + 
        "Stage 3: Extract Shoreline".center(100) + 
        f"\nUsing the following parameters: \n"+
        f"MACWE_iteration : {cfg.s3.MACWE_iteration}\n" +
        f"MACWE_smooth : {cfg.s3.MACWE_smooth}\n" +
        "\n" + "- " * 50 + "\n")

    if run_stage3:
        for save_folder, info in shores_2_extract.items():
            target_id, tidal_height, year = info["target_id"], info["tidal_height"], info["year"]
            bbox_idxs = glob(f"{save_folder}/s2A/best_bbox_ref_date/*.txt") 
            bbox_idxs = sorted([bbox_idx.split("/")[-1].split(".")[0] for bbox_idx in bbox_idxs], key=lambda x: int(x.split("_")[-1]))
            
            
            final_save_folder = save_folder.split("/")[-1] # f"{cfg.s0.suffix}_{target_id}_{year}_tide_{tidal_height}"
            # print(save_folder, final_save_folder)
            for sub_folder in ["PCA_Shoreline", 
                               "Kmeans_Shoreline", 
                               "Shoreline_evo", "RGB", "Uncertainty_map", "Norm_uncertainty_map"]:
                os.makedirs(f"{save_folder}/{final_save_folder}/{sub_folder}", exist_ok = True)
            
            
            print(f"Extracting shoreline for {target_id} - {year} - {tidal_height}")
            
            if one_by_one:
                for idx, bbox_idx in enumerate(bbox_idxs):
                    print(bbox_idx)
                    # img_4_kmeans, kmeans_result = \
                    s3_extract_shoreline(base_path,
                                        save_folder, 
                                        bbox_idx,
                                        final_save_folder,
                                        cfg.s3.MACWE_iteration,
                                        cfg.s3.MACWE_smooth,
                                        False,
                                        )
                    
                    # os._exit(0)
            else:
                with multiprocessing.Pool(min(os.cpu_count(), len(bbox_idxs), 5)) as pool:
                    inputs = []
                    for idx, bbox_idx in enumerate(bbox_idxs):
                        inputs.append((base_path, save_folder,  
                                       bbox_idx, 
                                       final_save_folder, 
                                       cfg.s3.MACWE_iteration, 
                                       cfg.s3.MACWE_smooth, 
                                       True
                                       ))
                        
                    pool.starmap(s3_extract_shoreline, inputs)
                    pool.close() ; pool.join()
            # break
    # endregion

    # endregion

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    
    parser.add_argument("--config", default = "auto_bbox_config.yaml", 
                        type = str, 
                        help = "YAML configuration file's name in the config folder.")
    
    args = parser.parse_args()
    main(args)
    
    """
    Usage:
    conda activate natshore
    python main.py --config auto_bbox_config.yaml
    python main.py --config pre_defined_config.yaml
    nohup python -u main.py --config auto_bbox_config.yaml &> log_UK_2019_2023_auto_bbox.txt &
    """