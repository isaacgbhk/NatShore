from datetime import datetime, timedelta
from osgeo import gdal, ogr, osr
from shapely.geometry import box
from shapely.wkb import loads as wkb_loads
from skimage import io
from skimage.segmentation import morphological_chan_vese, checkerboard_level_set
from skimage.transform import resize
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans

from shapely.geometry import Polygon, MultiPolygon
import geopandas as gpd
import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import time
import warnings

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

# region Helper functions
def date_range(central_date: str, before_days: int, after_days: int,
               fmt: str = "%Y-%m-%d") -> list[str]:
    """Return [start, end] date strings bracketing ``central_date`` by the given offsets.

    Args:
        central_date: Centre date string in ``fmt`` format.
        before_days: Days to subtract for the start date.
        after_days: Days to add for the end date.
        fmt: strptime/strftime format of ``central_date`` (default ``%Y-%m-%d``).
    """
    real = datetime.strptime(central_date, fmt)
    return [
        (real - timedelta(days=before_days)).strftime("%Y-%m-%d"),
        (real + timedelta(days=after_days)).strftime("%Y-%m-%d"),
    ]

def plot_all_imgs(list_of_imgs,dpii=150,axiss=True,x=12,y=18):
    # Subplots are organized in a Rows x Cols Grid
    # Tot and Cols are known
    plt.figure(figsize=(x,y),dpi=dpii) 
    plt.subplots_adjust()
    plt.tight_layout()
    
    Tot = len(list_of_imgs)
    Cols = 5 ############

    # Compute Rows required
    Rows = Tot // Cols 
    Rows += Tot % Cols

    # Create a Position index
    Position = range(1,Tot + 1)   
    
    # Create main figure
    fig = plt.figure(1)
    fig.tight_layout()
    for k in range(Tot):  # add every single subplot to the figure with a for loop
        ax = fig.add_subplot(Rows,Cols,Position[k])
        ax.imshow(list_of_imgs[k], cmap="gray")  # Or whatever you want in the subplot
        ax.axes.xaxis.set_visible(axiss) #
        ax.axes.yaxis.set_visible(axiss) #
        
    fig.tight_layout()
    plt.show()
    
def create_selected_CLOUDshapefile(in_dir_shp, out_dir_shp):  
    
    driver = ogr.GetDriverByName("ESRI Shapefile")
    dataSource = driver.Open(in_dir_shp, 1)
    input_layer = dataSource.GetLayer()    
    #print("original features #: "+str(input_layer.GetFeatureCount()))    
    
    input_layer.SetAttributeFilter('VALUEE = 2')  ### clouds were set to 2
    #print(input_layer.GetFeatureCount()) # how many features
        
    # Copy Filtered Layer and Output File
    out_ds = driver.CreateDataSource(out_dir_shp)
    out_layer = out_ds.CopyLayer(input_layer, str(99))
    
def array2geotif(pathAname, NParray, refGDALgeotiff, GDALtype=gdal.GDT_Byte, nband = 1):  # GDT_Byte = uint8
    # e.g., "H:/tifC500m/out8.tif", gdal.GDT_UInt16/GDT_Float32, class_prediction1[0], img_ds1

    out = gdal.GetDriverByName("GTiff").Create(pathAname, NParray.shape[1], NParray.shape[0], nband, GDALtype, ['COMPRESS=LZW'])
    
    out.SetProjection(refGDALgeotiff.GetProjection())     
    # create WGS84 Spatial Reference
    #sr = osr.SpatialReference()
    #sr.ImportFromEPSG(#####4326)
    #out.SetProjection(sr.ExportToWkt())

    out.SetGeoTransform(refGDALgeotiff.GetGeoTransform()) 
    out.GetRasterBand(1).WriteArray(NParray)
    out.FlushCache()  
    
def geotif2shp(in_geotiff_dir, in_geotiff_name, out_shp_dir, out_shp_name): #name with .tif and .shp!        
    
    src_ds = gdal.Open(in_geotiff_dir+in_geotiff_name)
    srcband = src_ds.GetRasterBand(1)
    
    drv = ogr.GetDriverByName("ESRI Shapefile")
    dst_ds = drv.CreateDataSource(out_shp_dir+out_shp_name)
    
    srss = ogr.osr.SpatialReference() 
    srss.ImportFromEPSG(3395)  ### set projection 'EPSG:4326' for WGS84; 3826 for TWD97; 3395 for Mercator
    
    dst_layer = dst_ds.CreateLayer(out_shp_dir+out_shp_name, srs = srss)
    newField = ogr.FieldDefn('VALUEE', ogr.OFTInteger) # a field to store RASTER's value
    dst_layer.CreateField(newField)
    
    gdal.Polygonize(srcband, None, dst_layer, 0, [], callback = None)
    #store value with the 4th para: 
    #https://gis.stackexchange.com/questions/92176/gdal-polygonize-in-python-creating-blank-polygon

def addfield_NAME(dir_shpfile, i, field = "BBOX_NAME"):
    driver = ogr.GetDriverByName("ESRI Shapefile")
    dataSource = driver.Open(dir_shpfile, 1)
    layer = dataSource.GetLayer()      
    
    new_field = ogr.FieldDefn(field, ogr.OFTInteger)
    layer.CreateField(new_field)

    for feature in layer:
        feature.SetField(field, i+1)
        layer.SetFeature(feature)      
        
def BBOXcoorsMAXMIN(RAWshorelineSHP):
    raw_lines = ogr.Open(RAWshorelineSHP)
    layer = raw_lines.GetLayer()
        
    LIST_W=[]
    LIST_E=[]
    LIST_S=[]
    LIST_N=[]
    
    for feature in layer:
        boundary = feature.GetGeometryRef().GetEnvelope() #.Boundary()
        #print(boundary) # (13376150.0, 13513650.0, 2717300.0, 2879100.0) w e s n
        LIST_W.append(boundary[0])
        LIST_E.append(boundary[1])
        LIST_S.append(boundary[2])
        LIST_N.append(boundary[3])
            
    MAXMIN=[min(LIST_W), max(LIST_E), min(LIST_S), max(LIST_N)]       
    return MAXMIN # LIST

def coors2pg(EnvelopeCoorTUPLE,outLINEshp):
    # Creating a line geometry
    linegeo = ogr.Geometry(ogr.wkbLineString)
    linegeo.AddPoint(EnvelopeCoorTUPLE[0],EnvelopeCoorTUPLE[2]) # W S
    linegeo.AddPoint(EnvelopeCoorTUPLE[0],EnvelopeCoorTUPLE[3]) # W N 
    linegeo.AddPoint(EnvelopeCoorTUPLE[1],EnvelopeCoorTUPLE[3]) # E N
    linegeo.AddPoint(EnvelopeCoorTUPLE[1],EnvelopeCoorTUPLE[2]) # E S
    linegeo.AddPoint(EnvelopeCoorTUPLE[0],EnvelopeCoorTUPLE[2]) # W S
    
    driver = ogr.GetDriverByName("ESRI Shapefile")
    ds = driver.CreateDataSource(outLINEshp)
    srs =  osr.SpatialReference()
    srs.ImportFromEPSG(3395)  ### Mercator
    layer = ds.CreateLayer('', srs, ogr.wkbLineString)

    # Add an ID field
    #idField = ogr.FieldDefn("id", ogr.OFTInteger)
    #layer.CreateField(idField)

    # Create the feature and set values
    featureDefn = layer.GetLayerDefn()
    feature = ogr.Feature(featureDefn)
    feature.SetGeometry(linegeo)
    #feature.SetField("id", 1)
    layer.CreateFeature(feature)

    feature = None
    # Save and close DataSource
    ds = None
    
def erase_shapes(to_erase, eraser, out_file):
    feat1 = ogr.Open(to_erase)
    feat2 = ogr.Open(eraser)
    feat1Layer = feat1.GetLayer()
    feat2Layer = feat2.GetLayer()

    driver = ogr.GetDriverByName('ESRI Shapefile')
    outDataSource = driver.CreateDataSource(out_file)
    outLayer = outDataSource.CreateLayer('', feat1Layer.GetSpatialRef(), feat1Layer.GetGeomType())

    out_ds = feat1Layer.Erase(feat2Layer, outLayer)
    out_ds = None

def addfield_AREAkm2(dir_shpfile):
    
    driver = ogr.GetDriverByName("ESRI Shapefile")
    dataSource = driver.Open(dir_shpfile, 1)
    layer = dataSource.GetLayer()
      
    
    new_field = ogr.FieldDefn("AreaKM2", ogr.OFTReal)
    new_field.SetWidth(32)
    new_field.SetPrecision(16)
    layer.CreateField(new_field)

    # Get the bounding box of the overall rectangle
    layer_extent = layer.GetExtent()
    min_x, max_x, min_y, max_y = layer_extent


    for feature in layer:

        geom = feature.GetGeometryRef()
        area_m2 = geom.GetArea()

        ##############################
        # [Original: Get the area of the polygon]
        # area_km2 = area_m2/1000000.0

        ##############################
        # [V2: Check if the geometry touches any of the edges of the overall rectangle]
        # In case the retangle contain the whole island, 
        # the ocean area will be the max area, and generated shapefile is not correct
        
        geom_extent = geom.GetEnvelope()  # Get the bounding box of the geometry
        geom_min_x, geom_max_x, geom_min_y, geom_max_y = geom_extent

        # Check if the geometry touches all of the edges of the overall rectangle
        touches_edge = (
            geom_min_x <= min_x and  # Touches left edge
            geom_max_x >= max_x and  # Touches right edge
            geom_min_y <= min_y and  # Touches bottom edge
            geom_max_y >= max_y     # Touches top edge
        )

        if touches_edge:
            area_km2 = 0.0  # Set area to 0 if it touches the edges
        else:
            area_m2 = geom.GetArea()
            area_km2 = area_m2 / 1000000.0
        ##############################

        feature.SetField("AreaKM2", area_km2)
        layer.SetFeature(feature)
        
#https://blog.csdn.net/qq_20373723/article/details/117220835
#https://gis.stackexchange.com/questions/169186/calculate-area-of-polygons-using-ogr-in-python-script

def pol2line(in_dir_PGshp, out_dir_LINEshp): #convert polygon to line
    """
    convert polygon to line
    :param in_dir_PGshp: the path of input, the shapefile of polygon
    :param out_dir_LINEshp: the path of output, the shapefile of line
    """
    driver = ogr.GetDriverByName('ESRI Shapefile')
    polyds = ogr.Open(in_dir_PGshp, 1)
    polyLayer = polyds.GetLayer()
    
    spatialref = polyLayer.GetSpatialRef()
    
    # create output
    lineds = driver.CreateDataSource(out_dir_LINEshp)
    linelayer = lineds.CreateLayer(out_dir_LINEshp, srs=spatialref, geom_type=ogr.wkbLineString)
    featuredefn = linelayer.GetLayerDefn()
    
    for feat in polyLayer:
        geom = feat.GetGeometryRef()
        ring = geom.GetGeometryRef(0)
        outfeature = ogr.Feature(featuredefn)
        outfeature.SetGeometry(ring)
        linelayer.CreateFeature(outfeature)
        outfeature = None        
        
#https://icode.best/i/82975937112677
   
def store_evolution_in(lst):
    def _store(x):
        lst.append(np.copy(x))
    return _store

def MorphACWE(image, checkerboard_level, MACWE_iteration, MACWE_smooth):
    init_ls = checkerboard_level_set(image.shape, checkerboard_level)

    # List with intermediate results for plotting the evolution
    evolution = []
    callback = store_evolution_in(evolution)

    #ls = morphological_chan_vese(image, iterations=MACWE_iteration, init_level_set=init_ls, 
    #                             smoothing=MACWE_smooth,iter_callback=callback)
    ls = morphological_chan_vese(image, 
                                 num_iter=MACWE_iteration, 
                                 init_level_set=init_ls, 
                                 smoothing=MACWE_smooth,
                                 iter_callback=callback
                                 )
    
    return ls, evolution  #final contour #contain each iteration's contour!  

def create_selected_ACMshapefile_max_overlap(input_vector_path, output_vector_path, target_area_gdf):
    """
    Selects the feature from an input vector file that covers the largest
    percentage of the total area defined by target_area_gdf.

    Args:
        input_vector_path (str): Path to the input vector file (e.g., shapefile).
        target_area_gdf (gpd.GeoDataFrame): GeoDataFrame containing the sea area polygon(s).
                                        Assumed to be in the desired CRS for analysis.
        output_vector_path (str): Path to save the selected feature (e.g., 'selected_feature.shp').
    """

    # print(f"Reading input features from: {input_vector_path}")
    try:
        input_gdf = gpd.read_file(input_vector_path)
    except Exception as e:
        print(f"ERROR: Could not read input file {input_vector_path}. Error: {e}")
        return None

    if input_gdf.empty:
        print("ERROR: Input GeoDataFrame is empty.")
        return None
    if target_area_gdf.empty:
        print("ERROR: Sea area GeoDataFrame is empty.")
        return None

    # --- CRS Handling ---
    # print(f"Input CRS: {input_gdf.crs}")
    # print(f"Sea Area CRS: {target_area_gdf.crs}")

    if input_gdf.crs != target_area_gdf.crs:
        print(f"Warning: CRS mismatch. Reprojecting input features to {target_area_gdf.crs}...")
        try:
            input_gdf = input_gdf.to_crs(target_area_gdf.crs)
            print("Reprojection successful.")
        except Exception as e:
            print(f"ERROR: Failed to reproject input GeoDataFrame. Error: {e}")
            return None
    else:
        print("CRS match. No reprojection needed.")

    # --- Area Calculation Warning ---
    if input_gdf.crs and input_gdf.crs.is_geographic:
        print(f"\nWarning: The CRS '{input_gdf.crs}' is geographic.")
        print("Area calculations will be in square degrees and may not be meaningful for overlap percentage.")
        print("Consider reprojecting both input_gdf and target_area_gdf to a suitable projected CRS (e.g., UTM or an equal-area projection) before running this function.\n")

    # --- Prepare Sea Area Geometry AND Calculate Total Sea Area ---
    try:
        # print("Dissolving sea area polygons...")
        # Dissolve sea polygons and get the single resulting geometry
        sea_geometry = target_area_gdf.dissolve().geometry.iloc[0]
        if not sea_geometry.is_valid:
            print("Warning: Dissolved sea area geometry is not valid, attempting buffer(0).")
            sea_geometry = sea_geometry.buffer(0)
        # print(f"Sea area geometry type after dissolve: {type(sea_geometry)}")

        # Calculate the TOTAL area of the dissolved sea geometry ONCE
        total_sea_area = sea_geometry.area
        # print(f"Total Sea Area calculated: {total_sea_area:.4f} (in CRS units squared)")

        # Handle case where sea area is zero or negligible
        if total_sea_area < 1e-9:
            print("ERROR: Total sea area is zero or negligible. Cannot calculate meaningful overlap percentages.")
            return None

    except Exception as e:
        print(f"ERROR: Could not dissolve sea area geometry or calculate its area. Error: {e}")
        return None

    # --- Calculate Overlap Percentage Relative to Sea Area ---
    print("Calculating intersections and overlap percentages relative to total sea area...")
    try:
        # Calculate the geometry of the intersection for each feature
        intersection_geoms = input_gdf.geometry.intersection(sea_geometry)

        # Calculate the area of the intersection
        # Use buffer(0) to handle potentially invalid intersection results
        input_gdf['intersection_area'] = intersection_geoms.buffer(0).area

        # Calculate overlap percentage relative to TOTAL sea area
        # (Intersection Area / Total Sea Area) * 100
        input_gdf['sea_overlap_percentage'] = (input_gdf['intersection_area'] / total_sea_area) * 100

    except Exception as e:
        print(f"ERROR: Failed during intersection or percentage calculation. Error: {e}")
        return None

    # --- Find Feature with Maximum Overlap Percentage ---
    if 'sea_overlap_percentage' not in input_gdf.columns or input_gdf['sea_overlap_percentage'].isnull().all():
        print("ERROR: Could not calculate sea overlap percentages or all are null.")
        return None

    try:
        # Get the index of the feature providing the maximum coverage of the sea area
        max_overlap_idx = input_gdf['sea_overlap_percentage'].idxmax()
        selected_feature_gdf = input_gdf.loc[[max_overlap_idx]].copy() # Keep as GeoDataFrame
    except ValueError:
        print("ERROR: Could not find feature with maximum sea overlap percentage (perhaps DataFrame empty or all overlaps NaN?).")
        return None

    print("-" * 30)
    print(f"Selected Feature Index: {max_overlap_idx}")
    print(f"Maximum Percentage of SEA AREA covered by this feature: {selected_feature_gdf['sea_overlap_percentage'].iloc[0]:.2f}%")
    # You might also want to see the absolute intersection area
    print(f"Absolute Intersection Area: {selected_feature_gdf['intersection_area'].iloc[0]:.4f}")
    # Optional: show original area of the selected feature for context
    # selected_feature_gdf['original_area'] = selected_feature_gdf.geometry.buffer(0).area
    # print(f"Selected Feature Original Area: {selected_feature_gdf['original_area'].iloc[0]:.4f}")
    print("-" * 30)

    # --- Save Output ---
    # Optional: Drop intermediate columns
    # columns_to_drop = ['intersection_area', 'sea_overlap_percentage', 'original_area'] # if you calculated original_area
    # selected_feature_gdf = selected_feature_gdf.drop(columns=columns_to_drop, errors='ignore')

    try:
        driver = None
        if output_vector_path.lower().endswith('.shp'):
            driver = 'ESRI Shapefile'
        elif output_vector_path.lower().endswith('.gpkg'):
            driver = 'GPKG'

        selected_feature_gdf.to_file(output_vector_path, driver=driver)
        print(f"Successfully saved selected feature to: {output_vector_path}")
        return selected_feature_gdf # Return the selected feature GDF
    except Exception as e:
        print(f"ERROR: Could not save output file {output_vector_path}. Error: {e}")
        return selected_feature_gdf # Return GDF even if save failed

def select_multiple_features_by_overlap(input_vector_path, output_vector_path, target_area_gdf, 
                                        min_total_coverage=0.9, 
                                        min_individual_overlap=0.10):
    import geopandas as gpd
    from shapely.ops import unary_union

    input_gdf = gpd.read_file(input_vector_path)
    if input_gdf.crs != target_area_gdf.crs:
        input_gdf = input_gdf.to_crs(target_area_gdf.crs)

    sea_geometry = target_area_gdf.dissolve().geometry.iloc[0]

    if not sea_geometry.is_valid:
        sea_geometry = sea_geometry.buffer(0)

    total_sea_area = sea_geometry.area
    input_gdf['intersection']  = input_gdf.geometry.intersection(sea_geometry)
    input_gdf['overlap_area']  = input_gdf['intersection'].area
    input_gdf['overlap_ratio'] = input_gdf['overlap_area'] / total_sea_area

    # Filter by individual overlap threshold
    filtered_gdf = input_gdf[input_gdf['overlap_ratio'] >= min_individual_overlap].copy()
    if filtered_gdf.empty:
        print("No features meet the minimum individual overlap threshold.")
        return None

    # Sort by overlap ratio descending
    filtered_gdf = filtered_gdf.sort_values(by='overlap_ratio', ascending=False)

    selected_features = []
    accumulated_area = 0.0

    for idx, row in filtered_gdf.iterrows():
        selected_features.append(row)
        accumulated_area += row['overlap_area']
        if accumulated_area / total_sea_area >= min_total_coverage:
            break

    selected_gdf = gpd.GeoDataFrame(selected_features, crs=filtered_gdf.crs)
    columns_to_drop = ['intersection', 'overlap_area', 'overlap_ratio']
    selected_gdf = selected_gdf.drop(columns=columns_to_drop)

    driver = 'ESRI Shapefile' if output_vector_path.endswith('.shp') else 'GPKG'
    selected_gdf.to_file(output_vector_path, driver=driver)
    print(f"Saved {len(selected_gdf)} features covering {accumulated_area / total_sea_area:.2%} of sea area.")

    return selected_gdf
    
def create_selected_ACMshapefile(in_dir_shp, out_dir_shp):      
    driver = ogr.GetDriverByName("ESRI Shapefile")
    dataSource = driver.Open(in_dir_shp, 1)
    input_layer = dataSource.GetLayer()    
    # print("original features #: "+str(input_layer.GetFeatureCount()))
    
    ## Filter 1: selecting ACM raster value = 1
    # input_layer.SetAttributeFilter('VALUEE = 1') #e.g., 'VALUEE = 1' # doesnt matter 1 or 0.... ACM gives random results
    # print(input_layer.GetFeatureCount()) # how many features
    
    ##################################################################################
    # [Original: Only output the MAX area]
    # Filter 2: selecting the MAX area
    area_s = []
    for feature in input_layer:
        area_s.append(feature.GetField("AreaKM2")) # defined by *addfield_AREAkm2*

    input_layer.SetAttributeFilter("AreaKM2 = "+str(max(area_s))) 
    print(input_layer.GetFeatureCount(), "Max area: "+str(max(area_s))) # how many features
    
    ##################################################################################
    # [New: Output the top N areas]
    ## Filter 2: selecting the top N areas
    # n_top=500
    # area_dict = {}
    # for feature in input_layer:
    #     fid = feature.GetFID()
    #     area = feature.GetField("AreaKM2")
    #     area_dict[fid] = area
    
    # # Sort by area and get top N FIDs
    # top_fids = sorted(area_dict.items(), key=lambda x: x[1], reverse=True)[:n_top]
    # fid_list = [str(fid) for fid, _ in top_fids]
    
    # # Create FID filter string
    # fid_filter = "FID IN (" + ",".join(fid_list) + ")"
    # input_layer.SetAttributeFilter(fid_filter)
    # print(f"Selected top {n_top} features: {input_layer.GetFeatureCount()}")

    ##################################################################################

    # Copy Filtered Layer and Output File
    out_ds = driver.CreateDataSource(out_dir_shp)
    out_layer = out_ds.CopyLayer(input_layer, str(99))
    
def detect_and_fill_edge_rectangle(arr, fill_value):
    # Finding the coordinates of the top-left and bottom-right corners of the rectangle
    rows, cols = np.where(arr == 1)
    if not len(rows) or not len(cols):
        return arr  # No rectangle found

    top_left = (min(rows), min(cols))
    bottom_right = (max(rows), max(cols))

    # Filling the inside of the rectangle, sparing the edges
    arr[top_left[0]+1:bottom_right[0], top_left[1]+1:bottom_right[1]] = fill_value
    return arr

def get_shoreline_mask(coor_bbox, shoreline_lines, new_size, shore_offset):
    
    # print(get_shoreline_mask.__name__)
    shoreline_lines.plot()
    
    # print(f"coor2 : {coor_bbox}")
    
    # Inertsection of the bbox and the shore
    bbox = box(coor_bbox[0][0], coor_bbox[0][1], coor_bbox[2][0], coor_bbox[2][1])
    bbox = gpd.GeoDataFrame(geometry=gpd.GeoSeries(bbox))
    
    # Get the intersection between the bbox (Polygon) and the shore (LineString)
    # Get the offseted shore
    intersection = gpd.overlay(shoreline_lines, bbox, how='intersection').buffer(shore_offset)
    intersection = gpd.GeoDataFrame(geometry=gpd.GeoSeries(intersection))
    intersection = gpd.overlay(intersection, bbox, how='intersection')
    
    fig, ax = plt.subplots(dpi = 3000)
    ax.axis('off')
    # intersection.set_crs(epsg=int(crss[-4:]), inplace=True)
    
    gpd.GeoDataFrame(geometry=gpd.GeoSeries(bbox.boundary[0])).plot(ax = ax, linewidth = 0.0, color = "k")
    intersection.plot(ax = ax)
    plt.show()
    
    fig.canvas.draw()
# !! offseted_shore
    offseted_shore_img = np.array(fig.canvas.renderer.buffer_rgba())
    # print(offseted_shore_img.shape)
    
    # Get the offseted shore
    fig, ax = plt.subplots(dpi = 3000)
    ax.axis('off')

    # Get the intersection between the bbox (Polygon) and the shore (LineString)
    intersection = gpd.overlay(shoreline_lines, bbox, how='intersection').buffer(shore_offset)
    intersection = gpd.GeoDataFrame(geometry=gpd.GeoSeries(intersection))
    intersection = gpd.overlay(intersection, bbox, how='intersection')
    
    gpd.GeoDataFrame(geometry=gpd.GeoSeries(bbox.boundary[0])).plot(ax = ax, linewidth = 0.3, color = "k")
    intersection.plot(ax = ax, color = "white")
    fig.canvas.draw()
# !! offseted_shore
    bbox_img = np.array(fig.canvas.renderer.buffer_rgba())
    bbox_arr = bbox_img[:, :, 0] < 255
    
    filled_bbox_arr = detect_and_fill_edge_rectangle(bbox_arr, 1)
    offseted_shore_img_filtered = offseted_shore_img.copy()[..., 0]
    rows, cols = np.where(filled_bbox_arr == 1)

    top_left = (min(rows), min(cols))
    bottom_right = (max(rows), max(cols))

    offseted_shore_img_filtered = offseted_shore_img_filtered[top_left[0]:bottom_right[0]+1, top_left[1]:bottom_right[1]+1]
    # Binary image
    offseted_shore_img_filtered = offseted_shore_img_filtered < 255

    offseted_shore_img_filtered = resize(offseted_shore_img_filtered, new_size)
    
    return offseted_shore_img_filtered

# endregion

def s3_extract_shoreline(
                         base_path         : str,
                         save_folder       : str,
                         bbox_idx          : str,
                         final_save_folder : str,
                         MACWE_iteration   : int,
                         MACWE_smooth      : int,
                         disable_print     : bool,
                         random_seed       : int = 42,
                         shore_folders     : str = "data/Shp_files/splitted_shoreline_polygon",
                         ) -> None:
    """
    Extract a shoreline from a downloaded satellite image using PCA and MACWE.

    Pipeline:
        1. Build a VRT from the GeoTIFF; generate RGB composite and cloud/nodata mask.
        2. PCA on all bands (retaining 90% explained variance) → first PC projection.
        3. Morphological Active Contours Without Edges (MACWE) on the PC1 projection.
        4. Polygon → line conversion, bbox-edge removal, area calculation.
        5. Export final shoreline shapefile to ``save_folder/<final_save_folder>/PCA_Shoreline/``.

    Args:
        base_path: Absolute path to the ``natshore/`` directory.
        save_folder: Run-specific output directory for this target/year/tide.
        bbox_idx: Identifier string ``<island_id>_<box_index>``.
        final_save_folder: Name of the final output sub-folder.
        MACWE_iteration: Number of MACWE evolution iterations.
        MACWE_smooth: MACWE smoothing parameter (1–4; larger = smoother).
        disable_print: Suppress INFO-level logging in worker processes.
        random_seed: Random seed for PCA and KMeans (ensures reproducibility).
    """
    if disable_print:
        logging.disable(logging.INFO)
        
    # region Set parameters
    
    bbox = open(f"{save_folder}/s2A/best_bbox_ref_date/{bbox_idx}.txt", "r").readlines()[1:][0].replace("(", "").replace(")", "").strip().split(", ")

    x1, y1, x2, y2, ref_ptx, ref_pty, best_date, best_height, best_fill, best_cloudless, order = bbox
    
    x1 = float(x1) ; y1 = float(y1) ; x2 = float(x2) ; y2 = float(y2)
    ref_ptx = float(ref_ptx) ; ref_pty = float(ref_pty)

    best_date = datetime.strptime(best_date, "%Y-%m-%d %H:%M:%S")
    best_date = best_date.strftime("%Y-%m-%d-%H-%M-%S")
    best_height = float(best_height)

    # print(f"bbox_idx: {bbox_idx}, save_folder: {save_folder}, MACWE_iteration: {MACWE_iteration}, MACWE_smooth: {MACWE_smooth}")
    # year = save_folder.split("/")[-1]
    
    sensor = "S2H"
    GEEresolution = 10.0                  # metres; Sentinel-2 native resolution
    threshold_explained_variance = 0.90   # PCA retains components explaining ≥90% variance
    projection, crss = "Mercator", "EPSG:3395"
    checkerboard_level = 5                # initial level-set for MACWE
    paraStr = f"{checkerboard_level}_{MACWE_iteration}_{MACWE_smooth}"
    shore_offset = 0.01

    ############################################################################################################

    Geedim_outimg_path = f"{save_folder}/s3/"
    raw_data_path = f"{save_folder}/s2B/data/" 

    # base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_id, bbox_i = bbox_idx.split("_")[0], int(bbox_idx.split("_")[1])

    shore_data = gpd.read_file(f"{base_path}/{shore_folders}/Shoreline_polygon_id_{target_id}")
    shoreline_lines = shore_data.boundary
    shoreline_lines = gpd.GeoDataFrame(geometry=gpd.GeoSeries(shoreline_lines))
        
    bbox = [[x1, y1], [x2, y1], [x2, y2], [x1, y2], [x1, y1]]    # region= {"type": "Polygon","coordinates": [bbox]}
    # print(bbox)
    # Crop the shoreline lines to the bbox
    # shoreline_lines = gpd.overlay(shoreline_lines, bbox, how='intersection')

    bbox_polygon = Polygon(bbox)
    bbox_gdf     = gpd.GeoDataFrame(geometry=[bbox_polygon], crs=shore_data.crs)
    shore_data   = shore_data.set_crs(bbox_gdf.crs)
    sea_area_gdf  = gpd.overlay(bbox_gdf, shore_data, how='difference')
    land_area_gdf = gpd.overlay(bbox_gdf, shore_data, how='intersection')


    TARGET_DATE        = best_date[0:10] # "2021-02-20-01-57-12" - > "2021-02-20"
    TARGET_DATEplus1   = (datetime.strptime(TARGET_DATE, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    start = time.time()
    out_name = str(bbox_idx) + "__" + sensor + "_geedim_" + TARGET_DATE + "_" + projection
                
    # endregion
    if os.path.exists(f"{save_folder}/{final_save_folder}/PCA_Shoreline/" + "PCA_" + out_name + "_1thPCA_ACMselecL_RMbbox.shp"):
        # and \
        # os.path.exists(f"{save_folder}/{final_save_folder}/" + out_name + "_Kmeans_ACMselecL_RMbbox.shp"):
        print(f"{out_name} File already exists, skipping...")
        return 
    
    # region STEP 3: make Cloud mask
    ############################## STEP 3: make Cloud mask ##############################
    # 3.1 read download geotiff
    tiffimg = raw_data_path + out_name + ".tif"
            
    # 3.2 make .vrt
    vrt = gdal.BuildVRT(Geedim_outimg_path + "_vrt/" + out_name + ".vrt",  # output
                        tiffimg,  # input
                        # separate=True, 
                        # callback=gdal.TermProgress_nocb
                        )
    
    # region Save RGB image
    im = io.imread(tiffimg)
    im = np.stack([im[3], im[2], im[1]], axis=-1)
    # Min-max normalization at each band
    for b in range(im.shape[2]):
        bmin, bmax = np.min(im[:, :, b]), np.max(im[:, :, b])
        b_img = (im[:, :, b] - bmin) / (bmax - bmin)
        b_img = np.power(b_img, 1/3)
        im[:, :, b] = b_img * 255
    
    
    rows, cols = im.shape[0], im.shape[1]
    bands = im.shape[2] if im.ndim == 3 else 1
    # print(f"rows: {rows}, cols: {cols}, bands: {bands}")
    
    pathAname = f"{save_folder}/{final_save_folder}/RGB/RGB_" + out_name + ".tif"
    
    # Create the output GeoTIFF file
    out = gdal.GetDriverByName("GTiff").Create(pathAname, cols, rows, bands, gdal.GDT_Byte, ['COMPRESS=LZW'])

    # Set the projection and geotransform from the reference GeoTIFF
    out.SetProjection(vrt.GetProjection())
    out.SetGeoTransform(vrt.GetGeoTransform())

    # Write each band to the output file
    for b in range(bands):
        out.GetRasterBand(b + 1).WriteArray(im[:, :, b] if bands > 1 else im)

    # Flush the cache to ensure data is written to disk
    out.FlushCache()
    del out 
    # endregion
    
    logger.info(" 3.1&2 VRT + RGB done, time: %.3f sec.", time.time() - start) ; start = time.time()

    # 3.3 generate nodata/cloud mask (band 0: 0 = missing, else = valid)
    imm = io.imread(tiffimg)[0, :, :]
    missing_mask = imm == 0

    cloud_pct = 100.0 * np.count_nonzero(imm == 0) / imm.size
    logger.info(" > Image shape: %s  nodata: %.2f%%", imm.shape, cloud_pct)

    imm[imm != 0] = 1
    imm[imm == 0] = 2  # create_selected_CLOUDshapefile expects: 1=valid, 2=nodata

    array2geotif(f"{Geedim_outimg_path}/_NODATA/" + out_name + "NODATA.tif", imm, vrt)
    del imm

    logger.info(" 3.3 Nodata mask done, time: %.3f sec.", time.time() - start) ; start = time.time()
    geotif2shp(f"{Geedim_outimg_path}/_NODATA/",  out_name + "NODATA.tif", f"{Geedim_outimg_path}/_NODATA/", out_name + "NODATA.shp") 
    # print(f"geotif2shp, time: {(time.time() - start):.{3}f} sec.") ; start = time.time()
    create_selected_CLOUDshapefile(f"{Geedim_outimg_path}/_NODATA/" + out_name + "NODATA.shp",
                                    f"{Geedim_outimg_path}/_NODATAselec/" + out_name + "NODATAselec.shp")
    logger.info(" 3.3 Nodata shapefile done, time: %.3f sec.", time.time() - start) ; start = time.time()

    # endregion 
    
    # region STEP 4: PCA analysis
    ############################## STEP 4: PCA analysis ##############################
    # 4.1 load all bands
    im = io.imread(tiffimg)
    layered_img = im

    # 4.2 reshape & standardise
    nbands, nx, ny      = layered_img.shape
    layered_img_shaped  = layered_img.reshape((nbands, nx * ny)) ; del layered_img
    scaler = StandardScaler()
    layered_img_shaped_rescaled = scaler.fit_transform(layered_img_shaped)
    del layered_img_shaped

    logger.info(" 4.1 Reshape/rescale done, time: %.3f sec.", time.time() - start) ; start = time.time()

    # 4.3 PCA — retain components explaining threshold_explained_variance of variance
    pca         = PCA(n_components=threshold_explained_variance, random_state=random_seed).fit(layered_img_shaped_rescaled.T)
    first_compo = pca.components_[0]
    pc1_proj    = (first_compo @ layered_img_shaped_rescaled).reshape(nx, ny)
    del layered_img_shaped_rescaled

    array2geotif(f"{Geedim_outimg_path}/PCA/" + out_name + "_1thPCA.tif", pc1_proj, vrt, gdal.GDT_Float32)
    logger.info(" 4.2 PCA done, time: %.3f sec.", time.time() - start) ; start = time.time()
    
    # endregion
    
    # region STEP 5: MACWE active contour on PCA projection
    ############################## STEP 5: MACWE ##############################
    ls_PCA, evo = MorphACWE(pc1_proj, checkerboard_level, MACWE_iteration, MACWE_smooth)
    
    # np.save(f"{save_folder}/{final_save_folder}/Shoreline_evo/evo_" + out_name + ".npy", evo)
    logger.info(" 5.1 MACWE done, time: %.3f sec.", time.time() - start) ; start = time.time()

    uncertainty_map = np.sqrt(pc1_proj**2)
    norm_uncertainty_map = uncertainty_map / np.max(uncertainty_map)
    
    uncertainty_map[missing_mask] = 0
    norm_uncertainty_map[missing_mask] = 0
    
    fig = plt.figure(dpi=250)
    plt.imshow(uncertainty_map, cmap="RdBu")
    plt.colorbar(orientation='vertical')
    plt.title(r"Uncertainty map ($\sqrt{PC1_{proj}^2}$)")

    ax = plt.gca()
    ax.set_aspect('equal')
    ax.axes.xaxis.set_visible(False)
    ax.axes.yaxis.set_visible(False)
    
    # plt.savefig(f"{Geedim_outimg_path}/PCA/" + out_name + f"_evo_ls.png")
    plt.savefig(f"{Geedim_outimg_path}/PCA/" + "uncertainty_map_" + out_name + f".png")
    plt.close()

    fig = plt.figure(dpi=250)
    plt.imshow(norm_uncertainty_map, cmap="RdBu")
    # Vertical colorbar
    plt.colorbar(orientation='vertical')
    plt.title(r"Uncertainty map Normalized ($\sqrt{PC1_{proj}^2}$)")
    
    ax = plt.gca()
    ax.set_aspect('equal')
    ax.axes.xaxis.set_visible(False)
    ax.axes.yaxis.set_visible(False)

    # plt.savefig(f"{Geedim_outimg_path}/PCA/" + out_name + f"_evo_ls.png")
    plt.savefig(f"{Geedim_outimg_path}/PCA/" + "norm_uncertainty_map_" + out_name + f".png")
    plt.close()

    
    # region Save RGB image
    rows, cols = norm_uncertainty_map.shape[0], norm_uncertainty_map.shape[1]
    bands = 1
    pathAname = f"{save_folder}/{final_save_folder}/Norm_uncertainty_map/norm_uncertainty_map_" + out_name + ".tif"
    out = gdal.GetDriverByName("GTiff").Create(pathAname, cols, rows, bands, gdal.GDT_Float32, ['COMPRESS=LZW'])
    out.SetProjection(vrt.GetProjection())
    out.SetGeoTransform(vrt.GetGeoTransform())
    out.GetRasterBand(1).WriteArray(norm_uncertainty_map)
    out.FlushCache()
    del out 
    
    bands = 1
    pathAname = f"{save_folder}/{final_save_folder}/Uncertainty_map/uncertainty_map_" + out_name + ".tif"
    out = gdal.GetDriverByName("GTiff").Create(pathAname, cols, rows, bands, gdal.GDT_Float32, ['COMPRESS=LZW'])
    out.SetProjection(vrt.GetProjection())
    out.SetGeoTransform(vrt.GetGeoTransform())
    out.GetRasterBand(1).WriteArray(uncertainty_map)
    out.FlushCache()
    del out 
    
    # endregion
    
    # 5.2 plot PCA projection with MACWE contour overlay
    plt.figure(dpi=250)
    plt.imshow(pc1_proj, cmap="rainbow")
    plt.colorbar()
    plt.contour(ls_PCA, linewidths=0.3, colors="black")
    ax = plt.gca()
    ax.set_aspect("equal")
    ax.axes.xaxis.set_visible(False)
    ax.axes.yaxis.set_visible(False)
    plt.title(f"BBOX{bbox_i + 1} {TARGET_DATE} [{paraStr}]")
    plt.savefig(f"{Geedim_outimg_path}/PCA/" + "PCA_1th_" + out_name + ".png")
    plt.close()

    logger.info(" 5.2 MACWE plot done, time: %.3f sec.", time.time() - start) ; start = time.time()
    # endregion
    
    # region STEP 6: Export tif & shp
    ############################## STEP 6: Export tif & shp ##############################
    array2geotif(f"{Geedim_outimg_path}/PCA_ACM/" + out_name + "_1thPCA_ACM.tif", ls_PCA, vrt)
    geotif2shp(f"{Geedim_outimg_path}/PCA_ACM/", out_name + "_1thPCA_ACM.tif",
               f"{Geedim_outimg_path}/PCA_ACM/", out_name + "_1thPCA_ACM.shp")

    addfield_AREAkm2(f"{Geedim_outimg_path}/PCA_ACM/" + out_name + "_1thPCA_ACM.shp")
    addfield_NAME(f"{Geedim_outimg_path}/PCA_ACM/" + out_name + "_1thPCA_ACM.shp", bbox_i)

    select_multiple_features_by_overlap(f"{Geedim_outimg_path}/PCA_ACM/" + out_name + "_1thPCA_ACM.shp",
                                    f"{Geedim_outimg_path}/PCA_ACMselec/" + out_name + "_1thPCA_ACMselec.shp",
                                    land_area_gdf)

    try:
        pol2line(f"{Geedim_outimg_path}/PCA_ACMselec/" + out_name + "_1thPCA_ACMselec.shp",
                 f"{Geedim_outimg_path}/PCA_ACMselecL/" + out_name + "_1thPCA_ACMselecL.shp")
    except Exception as e:
        logger.error("pol2line failed for %s: %s", bbox_idx, e)
        if disable_print:
            logging.disable(logging.NOTSET)
        return

    addfield_NAME(f"{Geedim_outimg_path}/PCA_ACMselecL/" + out_name + "_1thPCA_ACMselecL.shp", bbox_i)

    bbox = BBOXcoorsMAXMIN(f"{Geedim_outimg_path}/PCA_ACMselecL/" + out_name + "_1thPCA_ACMselecL.shp")
    coors2pg(bbox, f"{Geedim_outimg_path}/PCA_ACMselecL_bbox/" + out_name + "_1thPCA_ACMselecL_bbox.shp")

    erase_shapes(f"{Geedim_outimg_path}/PCA_ACMselecL/" + out_name + "_1thPCA_ACMselecL.shp",
                 f"{Geedim_outimg_path}/PCA_ACMselecL_bbox/" + out_name + "_1thPCA_ACMselecL_bbox.shp",
                 f"{Geedim_outimg_path}/PCA_ACMselecL_RMbbox/" + out_name + "_1thPCA_ACMselecL_RMbbox.shp")
    logger.info(" 6.1 Intermediate shapefile done")

    erase_shapes(f"{Geedim_outimg_path}/PCA_ACMselecL/" + out_name + "_1thPCA_ACMselecL.shp",
                 f"{Geedim_outimg_path}/PCA_ACMselecL_bbox/" + out_name + "_1thPCA_ACMselecL_bbox.shp",
                 f"{save_folder}/{final_save_folder}/PCA_Shoreline/" + "PCA_" + out_name + "_1thPCA_ACMselecL_RMbbox.shp")


    if disable_print:
        logging.disable(logging.NOTSET)
    
    # Append to the time log; retry once on concurrent write collision
    wrote = False
    while not wrote:
        try:
            with open(f"{save_folder}/s3_time_log.txt", "a") as f:
                f.write(f"{out_name}, {datetime.now()}\n")
            wrote = True
        except OSError:
            time.sleep(1)

    logger.info(" 6 Export done, time: %.3f sec. — %s", time.time() - start, out_name)
    # endregion