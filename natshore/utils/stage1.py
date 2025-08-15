from glob import glob
from math import radians, sin, cos, sqrt, atan2
from shapely.geometry import box, LineString, Point, Polygon
from shapely.geometry.multipolygon import MultiPolygon
from shapely.ops import nearest_points, polylabel
from tqdm import tqdm

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import os
import pandas as pd
import random
import time

from tpxo_tide_prediction import (read_parameter_file, tide_predict, write_tides)

# region Stage 1 util Functions
def random_color(): # Random color generator, one color and other lighter color
    r = lambda: random.randint(0,255)
    r, g, b = r(), r(), r()
    return ('#%02X%02X%02X' % (r,g,b), '#%02X%02X%02X' % (r//2,g//2,b//2), '#%02X%02X%02X' % (r//3,g//3,b//3))

def haversine_distance(coord1, coord2):
    R = 6371.0 # Earth radius in kilometers
    lat1, lon1 = radians(coord1[0]), radians(coord1[1])
    lat2, lon2 = radians(coord2[0]), radians(coord2[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c

def merge_section(data2merge, min_area_th_degree = 0.1, min_edge_th_km = 150):
    data = data2merge.copy()
    i = 0
    # Forward check
    while i < len(data) - 1:
        x1, y1, x2, y2 = LineString(data[i]).bounds
        area = (x2 - x1) * (y2 - y1)
        
        width = haversine_distance((x1, y1), (x2, y1))
        height = haversine_distance((x1, y1), (x1, y2))
        edges_greater_than_km_th = width > min_edge_th_km and height > min_edge_th_km
        
        # print(area < min_area_th_degree, not edges_greater_than_km_th)
        
        if area < min_area_th_degree and not edges_greater_than_km_th:
            # Add data[i] to data[i+1]
            data[i + 1] = data[i] + data[i + 1]
            data.pop(i)
            i -= 1
        i += 1

    # Backward check
    i = len(data) - 1
    while i > 0:
        x1, y1, x2, y2 = LineString(data[i]).bounds
        area = (x2 - x1) * (y2 - y1)
        
        width = haversine_distance((x1, y1), (x2, y1))
        height = haversine_distance((x1, y1), (x1, y2))
        edges_greater_than_km_th = width > min_edge_th_km and height > min_edge_th_km
        
        # print(area < min_area_th_degree, not edges_greater_than_km_th)
        if area < min_area_th_degree and not edges_greater_than_km_th:
            # Add data[i] to data[i-1]
            data[i - 1] = data[i] + data[i - 1]
            data.pop(i)
            i -= 1
        i -= 1

    return data

def merge_overlapping_sections(data, iou_th=0.5, mode = "forward"):
    merged_data = data.copy()
    
    # "forward":
    i = 0
    while i < len(merged_data) - 1:
        box1 = LineString(merged_data[i]).bounds
        box2 = LineString(merged_data[i + 1]).bounds
        
        poly1 = Polygon([(box1[0], box1[1]), (box1[2], box1[1]), (box1[2], box1[3]), (box1[0], box1[3])])
        poly2 = Polygon([(box2[0], box2[1]), (box2[2], box2[1]), (box2[2], box2[3]), (box2[0], box2[3])])
        
        if poly1.intersects(poly2):
            intersection = poly1.intersection(poly2).area
            area1 = poly1.area
            area2 = poly2.area
            
            if (intersection / area1 > iou_th) or (intersection / area2 > iou_th):
                # Merge the boxes by creating a new bounding box that encloses both
                new_box_coords = merged_data[i] + merged_data[i + 1]
                merged_data[i] = new_box_coords
                merged_data.pop(i + 1)
                continue  # Recheck the newly merged box with the next one
        i += 1
    
    # "backward":
    i = len(merged_data) - 1
    while i > 0:
        box1 = LineString(merged_data[i]).bounds
        box2 = LineString(merged_data[i - 1]).bounds
        
        poly1 = Polygon([(box1[0], box1[1]), (box1[2], box1[1]), (box1[2], box1[3]), (box1[0], box1[3])])
        poly2 = Polygon([(box2[0], box2[1]), (box2[2], box2[1]), (box2[2], box2[3]), (box2[0], box2[3])])
        
        if poly1.intersects(poly2):
            intersection = poly1.intersection(poly2).area
            area1 = poly1.area
            area2 = poly2.area
            
            if (intersection / area1 > iou_th) or (intersection / area2 > iou_th):
                # Merge the boxes by creating a new bounding box that encloses both
                new_box_coords = merged_data[i] + merged_data[i - 1]
                merged_data[i] = new_box_coords
                merged_data.pop(i - 1)
                continue
        i -= 1
    
    return merged_data

def remove_consecutive_integers(lst):
    filtered_list = [lst[0]]
    for i in range(1, len(lst)):
        if lst[i] != lst[i-1] + 1:
            filtered_list.append(lst[i])
    return filtered_list

def Random_Points_in_Polygon(polygon, number):
    points = []
    minx, miny, maxx, maxy = polygon.bounds
    while len(points) < number:
        pnt = Point(np.random.uniform(minx, maxx), np.random.uniform(miny, maxy))
        if polygon.contains(pnt):
            points.append(pnt)
    return points

# endregion

# region Stage 1 main Functions
def s1_auto_bbox_merge(river_path: str, shore_path: str, save_folder: str, base_path: str,
                       year               : int,
                       year_range         : int,
                       min_area_th_degree : float,        
                       min_edge_th_km     : float,    
                       max_area_th_degree : float,        
                       max_edge_th_km     : float,    
                       bbox_expand        : float,
                       shore_expand       : float,
                       shore_n_segments   : int,
                       min_dist_th        : float,
                       iou_th             : float,
                       tides_height_all   : dict ,
                       target_id          : str
                       ):
    """
    Stage 1 - Auto Bounding Box
    # Find BBox shoreline polygon by shoreline polygon + Merge BBox
    # Save the merged BBox as shapefile
    """
    
    river_data, shore_data = gpd.read_file(river_path), gpd.read_file(shore_path) 
    
    shoreline_lines = shore_data.boundary[0]
    shore_xy = list(shoreline_lines.coords)
    
    island_id = shore_data.id[0]
    
    # if os.path.exists(f"{save_folder}/s1/p_all_bbox_with_ref_pt_{island_id}.png"):
    #     print(f"    [s1] {island_id} already processed")
    #     return (tides_height_all, {})    
    
    river_id = river_path.split("/")[-1].split("-")[0].split("_")[-1]
    
    assert len(shore_data.geometry) == 1, 'shoreline_lines geometry length is not 1'
    
    start = time.time()
    
    #####################################################################################################################
    # region Get colosest point on shoreline   
    colosest_pts_island = []
    for river_idx in range(len(river_data)):
        colosest_point = nearest_points(shoreline_lines, Point(river_data.iloc[river_idx].geometry.coords[-1]))[0]
        min_dist = colosest_point.distance(Point(river_data.iloc[river_idx].geometry.coords[-1]))
        if min_dist < min_dist_th:
            colosest_pts_island.append(colosest_point)
            # colosest_pt_df = pd.concat([colosest_pt_df, pd.DataFrame([{'river_idx': river_data.iloc[river_idx].HYRIV_ID, 'colosest_pt': colosest_point, 'colosest_dist': min_dist}])])    
    
    # endregion
    
    #####################################################################################################################
    # region Get section of shoreline by closest points
    colosest_pts      = gpd.GeoSeries(colosest_pts_island)
    shoreline_pts     = [Point(shore_xy[i]) for i in range(len(shore_xy))]
    shoreline_pts_gdf = gpd.GeoDataFrame(geometry=gpd.GeoSeries(shoreline_pts))

    colosest_pts_idx, shore_pt_idx = shoreline_pts_gdf.sindex.nearest(colosest_pts, return_all=False, max_distance = 0.001)

    # Remove duplicate
    shore_pt_idx = sorted(list(set(shore_pt_idx)))
    # Remove consecutive integers
    shore_pt_idx = remove_consecutive_integers(shore_pt_idx)
    shore_pt_idx = np.concatenate((shore_pt_idx, [shore_pt_idx[-1] + shore_pt_idx[0]]))
    sections = []

    for idx in range(len(shore_pt_idx) - 1):
        sections.append(shoreline_pts[shore_pt_idx[idx] : shore_pt_idx[idx + 1] + 1 ])

    # Add last section connect head and tail
    head = shoreline_pts[shore_pt_idx[-1] : ]
    tail = shoreline_pts[0 : shore_pt_idx[0] + 1] if shore_pt_idx[0] != 0 else shoreline_pts[0 : 1]
    sections.append(head + tail)
    # Check if section is connected
    last_pt = sections[0][-1]

    for idx, section in enumerate(sections[1:]):
        assert section[0] == last_pt, f"Section {idx} is not connected"
        last_pt = section[-1]
    
    print(f"    [s1] Got {len(sections)} sections - Took {(time.time() - start):.2f} seconds") ; start = time.time()

    # endregion
    
    #####################################################################################################################
    # region Merge with area threshold and iou threshold
    merged_sections = merge_section(sections, min_area_th_degree = min_area_th_degree, min_edge_th_km = min_edge_th_km)
    print(f"    [s1] Merge to {len(merged_sections)} section with area threshold - Took {(time.time() - start):.2f} seconds") ; start = time.time()
    
    merged_sections_iou = merge_overlapping_sections(merged_sections, iou_th = iou_th)
    print(f"    [s1] Merge to {len(merged_sections_iou)} section with iou threshold - Took {(time.time() - start):.2f} seconds") ; start = time.time()
    
    expanded_sections = []
    #####################################################################################################################
    # Plot shorelines and bbox
    fig, ax = plt.subplots(figsize=(15, 15))
    ax.set_aspect('equal')
    areas = []
    
    
    # for idx, section in tqdm(enumerate(sections)):
    for idx, section in enumerate(sections): 
        line = LineString(section)
        plt.plot(*line.xy) #, label=f"Section {idx}")
        x1, y1, x2, y2 = line.bounds
        areas.append((x2 - x1) * (y2 - y1))
        
        x1 -= bbox_expand #(x2 - x1) * bbox_expand
        x2 += bbox_expand #(x2 - x1) * bbox_expand
        y1 -= bbox_expand #(y2 - y1) * bbox_expand
        y2 += bbox_expand #(y2 - y1) * bbox_expand
        
        # expanded_sections.append(box(x1, y1, x2, y2))
        # Random color
        plt.plot([x1, x2, x2, x1, x1], [y1, y1, y2, y2, y1], color = "orange")
            
    plt.title(f"Shoreline sections (ID = {island_id}) with bounding boxes (After Merge)), total {len(areas)} sections")
    # plt.subplot(1, 2, 2)
    # plt.hist(areas, bins=100)
    plt.title(f"Distribution of bounding box areas  (ID = {island_id}), total {len(areas)} sections")
    plt.tight_layout()
    plt.savefig(f"{save_folder}/s1/p_ori_sections_{island_id}.png") 
    plt.savefig(f"{save_folder}/s1/p_ori_sections_{island_id}.svg")
    # plt.close("all")
        
    #####################################################################################################################
    # Plot merged_sections_iou
    fig, ax = plt.subplots(figsize=(15, 15))
    ax.set_aspect('equal')
    areas = []
    
    # for idx, section in tqdm(enumerate(merged_sections_iou)):
    for idx, section in enumerate(merged_sections_iou): 
        line = LineString(section)
        plt.plot(*line.xy) #, label=f"Section {idx}")
        x1, y1, x2, y2 = line.bounds
        areas.append((x2 - x1) * (y2 - y1))
        
        x1 -= bbox_expand #(x2 - x1) * bbox_expand
        x2 += bbox_expand #(x2 - x1) * bbox_expand
        y1 -= bbox_expand #(y2 - y1) * bbox_expand
        y2 += bbox_expand #(y2 - y1) * bbox_expand
        
        expanded_sections.append(box(x1, y1, x2, y2))
        plt.plot([x1, x2, x2, x1, x1], [y1, y1, y2, y2, y1], color = "orange")
            
    plt.title(f"Shoreline sections (ID = {island_id}) with bounding boxes (After Merge)), total {len(areas)} sections")
    # plt.subplot(1, 2, 2)
    # plt.hist(areas, bins=100)
    plt.title(f"Distribution of bounding box areas  (ID = {island_id}), total {len(areas)} sections")
    plt.tight_layout()
    plt.savefig(f"{save_folder}/s1/p_merged_sections_iou_{island_id}.png")
    plt.savefig(f"{save_folder}/s1/p_merged_sections_iou_{island_id}.svg")
    
    np.save(f"{save_folder}/s1/section_{island_id}.npy",        np.array(sections, dtype = object))
    np.save(f"{save_folder}/s1/merged_section_{island_id}.npy", np.array(merged_sections_iou, dtype = object))
    np.save(f"{save_folder}/s1/merged_expanded_bbox_{island_id}.npy", np.array(expanded_sections, dtype = object))

    #####################################################################################################################
    # Bbox to shapefiles and txt
    bboxs          = [polygon.boundary for polygon in expanded_sections]
    gdf            = gpd.GeoDataFrame(geometry=bboxs)
    gdf.to_file(f"{save_folder}/s1/merged_bbox_shapefiles/{island_id}.shp", driver = 'ESRI Shapefile', crs = "EPSG:4326", engine = "fiona")
    
    print(f"        * Bbox shapefiles saved to -> {save_folder}/s1/merged_bbox_shapefiles/{island_id}.shp")
    
    text_to_save = ""
    
    for bbox in bboxs:
        x1, y1, x2, y2 = bbox.bounds
        text_to_save += f"{x1},{y1},{x2},{y2}\n"
        
    with open(f"{save_folder}/s1/merged_bbox_txt_{island_id}.txt",'w') as f: 
        f.writelines(text_to_save)
    
    print(f"        * Bbox txt saved to -> {save_folder}/s1/merged_bbox_txt_{island_id}.txt")
    
    # endregion

    #####################################################################################################################
    # region Find reference point, tide and plot
    start = time.time()
    
    sea_areas           = []
    ref_pt, ref_pt_idx, ref_pt_dist = [], [], []
    bbox_id = []
    
    # river_data, shore_data
    bbox_data_ply = gpd.GeoDataFrame(geometry=[box(*bbox.bounds) for bbox in gdf.geometry])
    
    shore_data_offset = shore_data.copy()
    shore_data_offset = shore_data_offset.to_crs(epsg=3857)
    shore_data_offset['geometry'] = shore_data_offset.geometry.buffer(shore_expand)
    shore_data_offset = shore_data_offset.to_crs(epsg=4326)
    
    polygon = shore_data_offset.geometry.iloc[0]
    line = LineString(list(polygon.exterior.coords))
    
    segment_length = line.length / shore_n_segments
    points = [line.interpolate(segment_length * i) for i in range(shore_n_segments)]

    if "Banda_Aceh" in save_folder:
        print("!!!!!!!!!!!!!!!!!")
        print("!!!!!!!!!!!!!!!!!")
        print("!!!!!!!!!!!!!!!!!")
        print(f"Using self-defined points for Banda_Aceh @ Indonesia")
        points = [
            Point((95.26690276694539, 5.568308025640956)),
            Point((0, 0))
        ]
        # For Banda_Aceh @ Indonesia

    time_range = pd.date_range(start = f"{year}-01-01T00:00:00", end = f"{year + year_range}-12-31T23:59:59", freq = "00h01min00s").astype("datetime64[s]") # Every 1 minute

    lats, lons = [], []
    for idx, point in enumerate(points):
        lats.append(point.y)
        lons.append(point.x)

    if f"{target_id}_{year}" not in tides_height_all:
        tide_All = tide_predict(f"{base_path}/data/Tide_height/TPXO9_atlas_nc/TPXO9_atlas_v5_nc", np.array(lats), np.array(lons), np.array(time_range))

        tide_stats = {
                        "lat"  : np.array(lats),
                        "lon"  : np.array(lons),
                        "tide" : list(tide_All.T),
                        "max"  : tide_All.max(0),
                        "min"  : tide_All.min(0),
                        "mean" : tide_All.mean(0),
                    }

        tide_stats_df = gpd.GeoDataFrame(tide_stats, 
                                         geometry=gpd.points_from_xy(tide_stats["lon"], 
                                                                     tide_stats["lat"])
                                                                     )
        tide_stats_df_valid = tide_stats_df[tide_stats_df["max"] != 0]
        tides_height_all[f"{target_id}_{year}"] = tide_stats_df_valid
    else:
        tide_stats_df_valid = tides_height_all[f"{target_id}_{year}"]
    
    fig, ax = plt.subplots(figsize=(15, 15))
    
    ax.set_title("Visualization of Main river, Shoreline and Bounding boxes with reference points")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    
    # tide_stats_df.plot(ax=ax, column="max", legend=True, legend_kwds={'label': "Tide height (m)"})
    # tide_stats_df[tide_stats_df["max"] == 0].plot(ax=ax, color="red", alpha=0.5)
    
    ref_pts = [tide_stats_df_valid.iloc[i].geometry for i in range(len(tide_stats_df_valid))]

    for idx, bbox in enumerate(bbox_data_ply.geometry):
        dists = [bbox.centroid.distance(ref_pt) for ref_pt in ref_pts]
        min_idx = np.argmin(dists)
        min_dist = dists[min_idx]
        
        ref_pt.append(ref_pts[min_idx])
        ref_pt_idx.append(min_idx)
        ref_pt_dist.append(min_dist)
        
        text_to_save = "x1, y1, x2, y2, ref_pt, ref_pt_idx, ref_pt_dist\n"
        text_to_save += f"{x1}, {y1}, {x2}, {y2}, ({ref_pt[-1].y}, {ref_pt[-1].x}), {ref_pt_idx[-1]}, {ref_pt_dist[-1]}\n"
        # sea_areas.append(sea_area)
        output_file = f"{save_folder}/s1/merge_bbox_ref_pt/{island_id}_{idx}.txt"
        bbox_id.append(f"{island_id}_{idx}")
        
        # Plot bbox and ref_pt + connect them with line
        x1, y1, x2, y2 = bbox.bounds
        plt.plot([x1, x2, x2, x1, x1], [y1, y1, y2, y2, y1], color = "orange")
        plt.plot(ref_pt[-1].x, ref_pt[-1].y, "ro")
        plt.plot([(x1 + x2)/2, ref_pt[-1].x], [(y1 + y2)/2, ref_pt[-1].y], "r--")
        
        with open(output_file, "w") as f:
            f.writelines(text_to_save)
        
    # return bbox_id, tide_stats_df_valid, bbox_data_ply, gdf
    
    print(f"    [s1] Reference point for each bbox found - Took {(time.time() - start):.2f} seconds") ; start = time.time()
    print(f"        * Reference point saved to -> {save_folder}/s1/merge_bbox_ref_pt")
    
    color = random_color()
    shore_data.plot(ax=ax, color=color[0], alpha=0.5)
    river_data.plot(ax=ax, color=color[1], alpha=0.5)
    gdf.plot(ax=ax,  color=color[2], alpha=0.5)

    plt.savefig(f"{save_folder}/s1/p_all_bbox_with_ref_pt_{island_id}.png")
    plt.savefig(f"{save_folder}/s1/p_all_bbox_with_ref_pt_{island_id}.svg")
    
    # endregion
    
    return (tides_height_all, 
            {"bbox_id"            : bbox_id, 
            "ref_pt"              : ref_pt, 
            "ref_pt_idx"          : ref_pt_idx, 
            "ref_pt_dist"         : ref_pt_dist, 
            "tide_stats_df_valid" : tide_stats_df_valid,
            })


def s1_predefined_bbox_merge(save_folder: str, base_path: str, year: int, year_range: int, tides_height_all: dict, target_id: str):

    print(f"    [s1] Predefined Bounding Box Merge")

    print(f"        * save_folder: {save_folder}")
    print(f"        * base_path: {base_path}")
    print(f"        * year: {year}")
    print(f"        * target_id: {target_id}")
    

    predefined_bbox_txt = sorted(glob(f"{save_folder}/s1/merge_bbox_ref_pt/*.txt")) 

    lats, lons, bbox_id = [], [], []
    ref_pt, ref_pt_idx, ref_pt_dist = [], [], []

    time_range = pd.date_range(start = f"{year}-01-01T00:00:00", end = f"{year + year_range}-12-31T23:59:59", freq = "00h01min00s").astype("datetime64[s]")

    predefined_bbox = []

    for txt_path in predefined_bbox_txt:
        with open(txt_path, "r") as f:
            lines = f.readlines()[1].replace(" ", "").replace("(", "").replace(")", "").split(",")

        x1, y1, x2, y2, single_ref_pt_x, single_ref_pt_y, single_ref_pt_idx, single_ref_pt_dist = list(map(float, lines))

        lons.append(single_ref_pt_x)
        lats.append(single_ref_pt_y)
        bbox_id.append(txt_path.split("/")[-1].split(".")[0])
        ref_pt.append(Point(single_ref_pt_x, single_ref_pt_y))
        ref_pt_idx.append(int(single_ref_pt_idx))
        ref_pt_dist.append(single_ref_pt_dist)
        
        predefined_bbox.append(box(x1, y1, x2, y2))

    if f"{target_id}_{year}" not in tides_height_all:
        tide_All = tide_predict(f"{base_path}/data/Tide_height/TPXO9_atlas_nc/TPXO9_atlas_v5_nc", np.array(lats), np.array(lons), np.array(time_range))

        # Add one more dimension to tide_All if it is 1D, in case of only single point
        if tide_All.ndim == 1:
            tide_All = tide_All[:, np.newaxis]

        tide_stats = {
                        "lat"  : np.array(lats),
                        "lon"  : np.array(lons),
                        "tide" : list(tide_All.T),
                        "max"  : tide_All.max(0),
                        "min"  : tide_All.min(0),
                        "mean" : tide_All.mean(0),
                    }
        
        tide_stats_df = gpd.GeoDataFrame(tide_stats, geometry=gpd.points_from_xy(tide_stats["lon"], tide_stats["lat"]))
        tide_stats_df_valid = tide_stats_df[tide_stats_df["max"] != 0]

        if tide_stats_df_valid.empty:
            print(f"        * All the predefined tidal reference points are not valid for {target_id} in {year}, please check the tide data")
            os._exit()

    #####################################################################################################################
    # Bbox to shapefiles and txt
    bboxs          = [polygon.boundary for polygon in predefined_bbox]
    gdf            = gpd.GeoDataFrame(geometry=bboxs)
    gdf.to_file(f"{save_folder}/s1/merged_bbox_shapefiles/{target_id}.shp", driver = 'ESRI Shapefile', crs = "EPSG:4326", engine = "fiona")
    
    print(f"        * Bbox shapefiles saved to -> {save_folder}/s1/merged_bbox_shapefiles/{target_id}.shp")
        
    return (tides_height_all, 
            {"bbox_id"            : bbox_id, 
            "ref_pt"              : ref_pt, 
            "ref_pt_idx"          : ref_pt_idx, 
            "ref_pt_dist"         : ref_pt_dist, 
            "tide_stats_df_valid" : tide_stats_df_valid,
            })