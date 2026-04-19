from datetime import datetime, timedelta
from shapely.geometry import box

import geedim as gd ; gd.Initialize()
import geopandas as gpd
import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd

from utils.utils import get_collection

logger = logging.getLogger(__name__)


def s2A_best_tide_date(bbox_idx            : str,
                      base_path           : str,
                      save_folder         : str,
                      year                : int,
                      year_range          : int,
                      tide_All            : np.array,
                      cloudless_portion   : int,
                      fill_portion        : int,
                      target_tidal_height : float,
                      mode                : str,
                      disable_print       : bool = False,
                      river_data_path     : str = "",
                      shore_data_path     : str = "",
                      ) -> None:
    """
    Find and save the best satellite acquisition date for a given bounding box.

    Searches the GEE catalog for scenes within the year window that satisfy
    cloud/fill thresholds, then selects the date whose tidal height is closest
    to ``target_tidal_height``. Results are written to
    ``save_folder/s2A/best_bbox_ref_date/<bbox_idx>.txt``.

    Args:
        bbox_idx: Identifier string ``<island_id>_<box_index>``.
        base_path: Absolute path to the ``natshore/`` directory.
        save_folder: Run-specific output directory for this target/year/tide.
        year: Start year of the search window.
        year_range: Number of additional years to include (0 = single year).
        tide_All: 1-D array of predicted tidal heights at 1-minute resolution.
        cloudless_portion: Minimum acceptable cloudless percentage (relaxed if needed).
        fill_portion: Minimum acceptable data-fill percentage (relaxed if needed).
        target_tidal_height: Desired tidal height in metres (e.g. 0.0 for MSL).
        mode: Pipeline mode (``auto_bbox`` | ``defined_bbox`` | ``defined_bbox_wo_ref``).
        disable_print: When True, suppress INFO-level log output (used in worker processes).
    """
    if disable_print:
        logging.disable(logging.INFO)

    if os.path.exists(f"{save_folder}/s2A/best_bbox_ref_date/{bbox_idx}.txt"):
        logger.info("Skipping %s — output already exists", bbox_idx)
        if disable_print:
            logging.disable(logging.NOTSET)
        return

    # region Get parameters

    target_id = bbox_idx.split("_")[0]

    with open(f"{save_folder}/s1/merge_bbox_ref_pt/{bbox_idx}.txt", "r") as fh:
        bbox_line = fh.readlines()[1:][0].replace("(", "").replace(")", "").strip()
    text_to_save = "x1, y1, x2, y2, lat, lon, datetimes, height, FILL, CLOUDLESS, order\n"

    x1, y1, x2, y2, lat, lon, ref_pt_idx, ref_pt_dist = [float(i) for i in bbox_line.split(",")]

    Geedim_collection = get_collection(year)

    coll   = gd.MaskedCollection.from_name(Geedim_collection)
    region = {"type": "Polygon", "coordinates": [[[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]]}

    good_table_split = []
    cond_switch      = 1
    best_height      = 100

    start_date = f"{year}-01-01T00:00:00"
    end_date   = f"{year + year_range}-12-31T23:59:59"

    time_range    = pd.date_range(start=start_date, end=end_date, freq="00h01min00s")
    time_range_dt = [datetime.strptime(str(i), "%Y-%m-%d %H:%M:%S") for i in time_range]

    logger.info("Searching dates — cloudless: %d%%, fill: %d%%, window: %s to %s",
                cloudless_portion, fill_portion, start_date, end_date)
    
    # endregion

    # region Get all good dates with cloudless and fill portion conditions
    search_start = datetime.now()
    
    coll_bbox = coll.search(start_date[:10], end_date[:10], region, fill_portion=40, cloudless_portion=40)

    good_table       = coll_bbox.properties_table.split("\n")[2:]
    good_table_split = [list(filter(None, s.split(" "))) for s in good_table]

    logger.info("Found %d candidate scenes in %s (%s → %s)",
                len(good_table_split), Geedim_collection, start_date[:10], end_date[:10])

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
            logger.info("Relaxing threshold — cloudless: %d%%, fill: %d%%", cloudless_portion, fill_portion)

        elif cond_switch == 2:
            fill_portion -= 5
            cond_switch = 1
            if fill_portion <= 40:
                break
            logger.info("Relaxing threshold — cloudless: %d%%, fill: %d%%", cloudless_portion, fill_portion)
            
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
        
       

        combined_ranks = rank_height
        
        sorted_combination_index = np.argsort(combined_ranks)
        best_combination_index = np.argmax(combined_ranks)
        # print("best_combination_index", best_combination_index)
        
        # best_height == closest to target_tidal_height (e.g. 0.0)
        best_height    = good_dates_height[best_combination_index]
        best_FILL      = good_dates_FILL[best_combination_index]
        best_CLOUDLESS = good_dates_CLOUDLESS[best_combination_index]

        best_date   = good_datetimes[best_combination_index]
        
    logger.info("Best date: %s  height: %.2f m  fill: %.1f%%  cloudless: %.1f%%",
                best_date, best_height, best_FILL, best_CLOUDLESS)
    
    # endregion
        
    for order, idx in enumerate(sorted_combination_index[::-1]):
        text_to_save += f"{x1}, {y1}, {x2}, {y2}, {lat}, {lon}, {good_datetimes[idx]}, {good_dates_height[idx]}, {good_dates_FILL[idx]}, {good_dates_CLOUDLESS[idx]}, {order}\n"

    # region Plot map and bbox
    # subfigures 

    plot_time_series = True
    
    if plot_time_series:
        fig, axs = plt.subplots(1, 2, figsize=(25, 10))

        axs[0].plot(time_range, tide_All, color="b", label="Tide Height", zorder=1)

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

        if mode == "auto_bbox" and river_data_path and shore_data_path:
            river_data = gpd.read_file(river_data_path)
            shore_data = gpd.read_file(shore_data_path)
            
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
    with open(output_file, "w") as f:
        f.writelines(text_to_save)
    logger.info("Saved best-date results → %s", output_file)

    if disable_print:
        logging.disable(logging.NOTSET)
    # endregion