from datetime import datetime, timedelta
from shapely.geometry import box

import geedim as gd ; gd.Initialize()
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import os
import sys
import pandas as pd


def s2A_best_tide_date(bbox_idx            : str, 
                      base_path           : str, 
                      save_folder         : str, 
                      year                : int, 
                      year_range          : int,
                      tide_All            : np.array,
                      cloudless_portion   : int, 
                      fill_portion        : int, 
                      target_tidal_height : float, 
                    #   Geedim_collection   : str, 
                      mode                : str,
                      disable_print       : bool = False,
                      ):
    """
    Stage 2A - Best Tide & Date data
    # Find best tide date with cloudless and fill portion conditions
    """
    if disable_print: 
        sys.stdout = open(os.devnull, 'w')
        
    if os.path.exists(f"{save_folder}/s2A/best_bbox_ref_date/{bbox_idx}.txt"):
        print(f"Skipping {bbox_idx} as it already exists")
        return
    
    # region Get parameters
    
    target_id = bbox_idx.split("_")[0]

    bbox = open(f"{save_folder}/s1/merge_bbox_ref_pt/{bbox_idx}.txt", "r").readlines()[1:][0].replace("(", "").replace(")", "").strip()
    text_to_save = f"x1, y1, x2, y2, lat, lon, datetimes, height, FILL, CLOUDLESS, order\n"

    x1, y1, x2, y2, lat, lon, ref_pt_idx, ref_pt_dist = [float(i) for i in bbox.split(",")]

    # Geedim_collection = "COPERNICUS/S2_SR_HARMONIZED" if year >= 2018 else "LANDSAT/LC08/C02/T1_L2"

    if year >= 2018:
        Geedim_collection = "COPERNICUS/S2_SR_HARMONIZED"
    elif year >= 2013:
        Geedim_collection = "LANDSAT/LC08/C02/T1_L2"
    elif year >= 1984:
        Geedim_collection = "LANDSAT/LT05/C02/T1_L2"
    else:
        raise ValueError("Year must be >= 1984 for Landsat or >= 2018 for Sentinel-2")

    coll   = gd.MaskedCollection.from_name(Geedim_collection)
    region = {"type": "Polygon", "coordinates": [[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]]}

    good_table_split = []
    cond_switch      = 1
    best_height      = 100
    
    start_date = f"{year}-01-01T00:00:00"
    end_date   = f"{year + year_range}-12-31T23:59:59"

    start_run = datetime.now()

    # time_range    = pd.date_range(start = f"{year}-01-01T00:00:00", end = f"{year + year_range}-12-31T23:59:59", freq = "00h01min00s") # Every 1 minute
    time_range = pd.date_range(start = f"{year}-01-01T00:00:00", end = f"{year + year_range}-12-31T23:59:59", freq = "00h01min00s") # Every 1 minute
    time_range_dt = [datetime.strptime(str(i), "%Y-%m-%d %H:%M:%S") for i in time_range]

    print(f"Searcing for good dates with cloudless_portion: {cloudless_portion}, fill_portion: {fill_portion}, {start_date, end_date}")
    
    # endregion

    # region Get all good dates with cloudless and fill portion conditions
    search_start = datetime.now()
    
    coll_bbox = coll.search(start_date[:10], end_date[:10], region, fill_portion = 40, cloudless_portion = 40)
    # print(start_date[:10], end_date[:10], region)
        
    # print(f"Search completed in {datetime.now() - search_start}")

    # Parse the properties table
    good_table       = coll_bbox.properties_table.split("\n")[2:]
    good_table_split = [filter(None, s.split(" ")) for s in good_table]
    good_table_split = [list(filtered) for filtered in good_table_split]

    # lat_pred, lon_pred, times = read_parameter_file(f"{save_folder}/s2A/{year}_tide_time.txt", lat, lon)
    # tide_All                  = tide_predict(f"{base_path}/data/Tide_height/TPXO9_atlas_nc/TPXO9_atlas_v5_nc", lat_pred, lon_pred, times)

    print(f"Got {len(good_table_split)} good dates, with {Geedim_collection}, within {start_date[:10]} and {end_date[:10]}, and region {region}")

    good_datetimes       = []
    good_dates_FILL      = []
    good_dates_CLOUDLESS = []
    rank_FILL            = []
    rank_CLOUDLESS       = []

    while len(good_table_split) == 0 or abs(best_height) > 0.10: # 10 cm error tolerance
        
        good_datetimes_temp       = []
        good_dates_FILL_temp      = []
        good_dates_CLOUDLESS_temp = []

        for i in good_table_split:
            if float(i[3]) >= fill_portion and float(i[4]) >= cloudless_portion:
                good_datetimes_temp.append(datetime.strptime(f"{i[1]} {i[2]}:00", "%Y-%m-%d %H:%M:%S"))
                good_dates_FILL_temp.append(float(i[3]))
                good_dates_CLOUDLESS_temp.append(float(i[4]))
        
        if cond_switch == 1:
            cloudless_portion -= 5
            cond_switch = 2
            if cloudless_portion <= 40: 
                break
            print(f"Condition changed!, cloudless_portion: {cloudless_portion}, fill_portion: {fill_portion}")      
                
        elif cond_switch == 2:
            fill_portion -= 5
            cond_switch = 1
            if fill_portion <= 40: 
                break
            print(f"Condition changed!, cloudless_portion: {cloudless_portion}, fill_portion: {fill_portion}")
            
        if len(good_datetimes_temp) == 0:
            continue
        
        good_datetimes       = []
        good_dates_FILL      = []
        good_dates_CLOUDLESS = []
        
        # Remove duplicates
        for date, fill, cloudless in zip(good_datetimes_temp, good_dates_FILL_temp, good_dates_CLOUDLESS_temp):
            if date not in good_datetimes:
                good_datetimes.append(date)
                good_dates_FILL.append(fill)
                good_dates_CLOUDLESS.append(cloudless)
            else: 
                good_dates_FILL[-1] = max(good_dates_FILL[-1], fill)
                good_dates_CLOUDLESS[-1] = max(good_dates_CLOUDLESS[-1], cloudless)
        
        good_dates_height = [tide_All[i] for i in range(len(time_range_dt)) if time_range_dt[i] in good_datetimes]
        
        
        FILL_rank      = sorted(np.unique(good_dates_FILL)) #, reverse = True)
        CLOUDLESS_rank = sorted(np.unique(good_dates_CLOUDLESS)) #, reverse = True)
        
        rank_height    = len(good_dates_height) - np.argsort(np.argsort(np.abs(np.array(good_dates_height) - target_tidal_height)))
        rank_FILL      = [FILL_rank.index(good_dates_FILL[i]) for i in range(len(good_dates_FILL))]
        rank_CLOUDLESS = [CLOUDLESS_rank.index(good_dates_CLOUDLESS[i]) for i in range(len(good_dates_CLOUDLESS))]
        
       

        # rank_FILL      = len(good_dates_height) - np.argsort(np.argsort(-np.array(good_dates_FILL)))
        # rank_CLOUDLESS = len(good_dates_height) - np.argsort(np.argsort(-np.array(good_dates_CLOUDLESS)))
        
        # print("height: ", len(rank_height), good_dates_height, rank_height)
        # print("CLOUDLESS: ", len(rank_CLOUDLESS), good_dates_CLOUDLESS, rank_FILL)
        # print("FILL: ", len(rank_FILL), good_dates_FILL, rank_CLOUDLESS)
        
        # combined_ranks = 2 * rank_height + rank_FILL + rank_CLOUDLESS
        combined_ranks = rank_height  
        # combined_ranks = rank_CLOUDLESS + rank_height + rank_FILL
        # print(combined_ranks, "combined_ranks")
        
        sorted_combination_index = np.argsort(combined_ranks)
        best_combination_index = np.argmax(combined_ranks)
        # print("best_combination_index", best_combination_index)
        
        # best_height == closest to target_tidal_height (e.g. 0.0)
        best_height    = good_dates_height[best_combination_index]
        best_FILL      = good_dates_FILL[best_combination_index]
        best_CLOUDLESS = good_dates_CLOUDLESS[best_combination_index]

        best_date   = good_datetimes[best_combination_index]
        
    # return good_dates_height, good_dates_FILL, good_dates_CLOUDLESS, best_date, best_height, best_FILL, best_CLOUDLESS, sorted_combination_index
    # print(coll_bbox.properties_table)
    # print(f"Got {len(good_table_split)} good dates")

    # for idx in range(len(good_table_split)):
        
    print("FILL:", good_dates_FILL, rank_FILL)
    print("CLOUDLESS:", good_dates_CLOUDLESS, rank_CLOUDLESS)
    
    # endregion
        
    for order, idx in enumerate(sorted_combination_index[::-1]):
        text_to_save += f"{x1}, {y1}, {x2}, {y2}, {lat}, {lon}, {good_datetimes[idx]}, {good_dates_height[idx]}, {good_dates_FILL[idx]}, {good_dates_CLOUDLESS[idx]}, {order}\n"
        
    # text_to_save += f"{x1}, {y1}, {x2}, {y2}, {lat}, {lon}, {best_date}, {best_height}\n"
    # print("text_to_save", text_to_save)

    # region Plot map and bbox
    # subfigures 

    plot_time_series = True
    
    if plot_time_series:
        fig, axs = plt.subplots(1, 2, figsize=(25, 10))
        # fig = plt.figure(figsize = (20,10)) 

        # start_date    = f"{year}-01-01T00:00:00"
        # end_date      = f"{year}-12-31T23:59:59"
        # time_range    = pd.date_range(start = start_date, end = end_date, freq = "00H01T00S")

        axs[0].plot(time_range, tide_All, color = "b", label = "Tide Height", zorder=1)

        axs[0].scatter(good_datetimes, good_dates_height, color = "k", label = "Good Dates", zorder=2)
        axs[0].text(best_date + timedelta(days = 7), best_height + 0.05, 
                    f"""Best Date: {best_date}
                    \nBest Height: {best_height:.2f}
                    \nBest FILL: {best_FILL:.2f}
                    \nBest CLOUDLESS: {best_CLOUDLESS:.2f}
                    """, 
                    fontsize=15, color = "orange")
        axs[0].scatter(best_date, best_height, color = "orange", label = "Best Date", zorder=3, s = 100)

        axs[0].set_xlabel("Time")
        axs[0].set_ylabel("Tide Height (meters)")

        axs[0].set_title(f"[x1: {x1:.2f}, y1: {y1:.2f}, x2: {x2:.2f}, y2: {y2:.2f}]\nref_pt_x: {lon:.2f}, ref_pt_y: {lat:.2f}, ref_pt_dist: {ref_pt_dist:.2f} - Height Variation")
        axs[0].legend()
        axs[0].grid(True)

        if mode == "auto_bbox":
            river_data = gpd.read_file(f"{base_path}/data/Shp_files/splitted_river_linstring/River_Linestring_0_id_{target_id}")
            shore_data = gpd.read_file(f"{base_path}/data/Shp_files/splitted_shoreline_polygon/Shoreline_polygon_id_{target_id}")
            
            river_data.plot(ax = axs[1])
            shore_data.plot(ax = axs[1])

        # Bbox from x1, y1, x2, y2
        b = box(x1, y1, x2, y2)
        
        axs[1].set_aspect("equal")
        axs[1].plot(*b.exterior.xy, color="orange")
        axs[1].scatter(lon, lat, color = "r", label = "Reference Point", zorder=3, s = 20)
        axs[1].set_title("Target area and corresponding bbox")

        plt.tight_layout()
        plt.savefig(f"{save_folder}/s2A/tide_height/p_{bbox_idx}_h{best_height:.2f}_f_{best_FILL:.2f}_c{best_CLOUDLESS:.2f}.png")
        # plt.savefig(f"{save_folder}/s2A/tide_height/p_{bbox_idx}_h{best_height:.2f}_f_{best_FILL:.2f}_c{best_CLOUDLESS:.2f}.svg")
        
        plt.close()


    output_file = f"{save_folder}/s2A/best_bbox_ref_date/{bbox_idx}.txt"

    print(f"output_file: {output_file}")
    with open(output_file, 'w') as f:
        f.writelines(text_to_save)
        
    # sys.stdout = open(os.devnull, 'w')    
    if disable_print: 
        sys.stdout = sys.__stdout__
    
    # print(f"Task {bbox_idx} completed in {datetime.now() - start_run}, {datetime.now()}")
    # endregion