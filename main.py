import argparse
import logging
import multiprocessing
import os
import shutil
from glob import glob

import ee
import matplotlib.pyplot as plt
from tqdm import tqdm

from configs.config import convert
from utils.stage1 import s1_auto_bbox_merge, s1_predefined_bbox_merge
from utils.stage2A import s2A_best_tide_date
from utils.stage2B import s2B_geedim_download
from utils.stage3 import s3_extract_shoreline
from utils.utils import init_setup

logger = logging.getLogger(__name__)

_FINAL_SUBFOLDERS = [
    "PCA_Shoreline", "RGB", "Uncertainty_map", "Norm_uncertainty_map",
]


def _bbox_idxs_from_folder(folder: str) -> list[str]:
    """Return sorted bbox identifiers from Stage 2A output text files."""
    txts = glob(f"{folder}/s2A/best_bbox_ref_date/*.txt")
    return sorted(
        [os.path.splitext(os.path.basename(t))[0] for t in txts],
        key=lambda x: int(x.split("_")[-1]),
    )


def main(args: argparse.Namespace) -> None:
    # ── Stage 0: setup ──────────────────────────────────────────────────────
    base_path   = os.path.dirname(__file__)
    config_path = os.path.join(base_path, "configs", args.config)

    cfg = convert(config_path)
    cfg = cfg._replace(base_path=base_path)

    # Initialise GEE with the project ID from config
    gee_project = getattr(cfg.s0, "gee_project", "")
    if gee_project:
        ee.Initialize(project=gee_project)

    # Determine which stages run
    run_stage1N2A = "1" in args.stages or "2A" in args.stages
    run_stage2B   = "2B" in args.stages
    run_stage3    = "3" in args.stages

    # defined_bbox_wo_ref always skips Stage 1 and 2A
    if cfg.s0.mode == "defined_bbox_wo_ref":
        run_stage1N2A = False
        run_stage2B   = True if not args.stages else run_stage2B
        run_stage3    = True if not args.stages else run_stage3

    last_checkpoint = not args.new_run
    max_workers     = getattr(cfg.s0, "max_workers", 5)
    random_seed     = getattr(cfg.s0, "random_seed", 42)

    shores_2_extract = init_setup(base_path, cfg, last_checkpoint)

    for save_folder in shores_2_extract:
        logger.info("[s0] %s", save_folder)
        shutil.copy2(config_path, save_folder)

    # ── Stage 1: bounding boxes ─────────────────────────────────────────────
    if run_stage1N2A:
        logger.info("=" * 80)
        logger.info("Stage 1: Bounding Box  [area: %s–%s °²  edge: %s–%s km]",
                    cfg.s1.min_area_th_degree, cfg.s1.max_area_th_degree,
                    cfg.s1.min_edge_th_km, cfg.s1.max_edge_th_km)

        tides_height_all = {}

        for save_folder, info in shores_2_extract.items():
            target_id, tidal_height, year = info["target_id"], info["tidal_height"], info["year"]

            if cfg.s0.mode == "auto_bbox":
                logger.info("  * %s", save_folder.split("/")[-3:])
                river_matches = glob(os.path.join(base_path, cfg.s0.river_folders, f"*id_{target_id}"))
                shore_matches = glob(os.path.join(base_path, cfg.s0.shore_folders, f"*id_{target_id}"))
                if not river_matches:
                    raise FileNotFoundError(
                        f"No river data found for target_id={target_id} in {cfg.s0.river_folders}"
                    )
                if not shore_matches:
                    raise FileNotFoundError(
                        f"No shore data found for target_id={target_id} in {cfg.s0.shore_folders}"
                    )
                river_data_path = river_matches[0]
                shore_data_path = shore_matches[0]
                shores_2_extract[save_folder]["river_data_path"] = river_data_path
                shores_2_extract[save_folder]["shore_data_path"] = shore_data_path
                tides_height_all, s1_results = s1_auto_bbox_merge(
                    river_data_path, shore_data_path, save_folder, base_path,
                    year, cfg.s0.year_range,
                    min_area_th_degree=cfg.s1.min_area_th_degree,
                    min_edge_th_km=cfg.s1.min_edge_th_km,
                    max_area_th_degree=cfg.s1.max_area_th_degree,
                    max_edge_th_km=cfg.s1.max_edge_th_km,
                    bbox_expand=cfg.s1.bbox_expand, shore_expand=cfg.s1.shore_expand,
                    shore_n_segments=cfg.s1.shore_n_segments,
                    min_dist_th=cfg.s1.min_dist_th, iou_th=cfg.s1.iou_th,
                    tides_height_all=tides_height_all, target_id=target_id,
                    tidal_model=cfg.s1.tidal_model,
                )

            elif cfg.s0.mode == "defined_bbox":
                logger.info("  * defined_bbox: %s", save_folder.split("/")[-3:])
                tides_height_all, s1_results = s1_predefined_bbox_merge(
                    save_folder, base_path, year, cfg.s0.year_range,
                    tides_height_all, target_id,
                    tidal_model=cfg.s1.tidal_model,
                )

            elif cfg.s0.mode == "defined_bbox_wo_ref":
                predefined_bbox_txt = sorted(glob(f"{save_folder}/s1/merge_bbox_ref_pt/*.txt"))
                s1_results = {
                    "bbox_id"            : [os.path.splitext(os.path.basename(t))[0] for t in predefined_bbox_txt],
                    "ref_pt_idx"         : list(range(len(predefined_bbox_txt))),
                    "ref_pt_dist"        : [0.0] * len(predefined_bbox_txt),
                    "tide_stats_df_valid": [],
                }

            shores_2_extract[save_folder]["s1_results"] = s1_results
            plt.close("all")

        del tides_height_all

    # ── Stage 2A: best date selection ───────────────────────────────────────
    if run_stage1N2A:
        logger.info("=" * 80)
        logger.info("Stage 2A: Best Date  [target heights: %s  years: %s]",
                    cfg.s0.target_tidal_height, cfg.s0.year)

        for save_folder, info in shores_2_extract.items():
            target_id, tidal_height, year = info["target_id"], info["tidal_height"], info["year"]
            logger.info("  * %s", save_folder.split("/")[-3:])

            s1_results = shores_2_extract[save_folder]["s1_results"]
            bbox_idxs  = s1_results["bbox_id"]

            tide_all = list(s1_results["tide_stats_df_valid"]["tide"])
            tides    = [tide_all[i] for i in s1_results["ref_pt_idx"]]

            river_data_path = info.get("river_data_path", "")
            shore_data_path = info.get("shore_data_path", "")

            inputs = [
                (bbox_idx, base_path, save_folder, year, cfg.s0.year_range,
                 tide, cfg.s2A.cloudless_portion, cfg.s2A.fill_portion, tidal_height,
                 cfg.s0.mode, True, river_data_path, shore_data_path)
                for bbox_idx, tide in zip(bbox_idxs, tides)
            ]
            with multiprocessing.Pool(processes=min(os.cpu_count(), len(bbox_idxs), max_workers)) as pool:
                pool.starmap(s2A_best_tide_date, tqdm(inputs, total=len(inputs)))

            logger.info("  * Completed %s", save_folder.split("/")[-3:])

    # ── Stage 2B: download ───────────────────────────────────────────────────
    if run_stage2B:
        logger.info("=" * 80)
        logger.info("Stage 2B: Download  [years: %s]", cfg.s0.year)

        for save_folder, info in shores_2_extract.items():
            target_id, tidal_height, year = info["target_id"], info["tidal_height"], info["year"]
            bbox_idxs = _bbox_idxs_from_folder(save_folder)
            logger.info("  bbox_idxs: %s", bbox_idxs)

            downloaded = 0
            while downloaded < len(bbox_idxs):
                downloaded = len(glob(f"{save_folder}/s2B/data/*.tif"))
                logger.info("  Downloaded: %d / %d", downloaded, len(bbox_idxs))
                inputs = [(save_folder, bbox_idx, year, target_id) for bbox_idx in bbox_idxs]
                # with multiprocessing.Pool(min(os.cpu_count(), len(bbox_idxs), max_workers)) as pool:
                #     pool.starmap(s2B_geedim_download, tqdm(inputs, total=len(inputs)))
                
                for input in inputs:
                    s2B_geedim_download(*input)
                    downloaded = len(glob(f"{save_folder}/s2B/data/*.tif"))
                    logger.info("  Downloaded: %d / %d", downloaded, len(bbox_idxs))

    # ── Stage 3: shoreline extraction ───────────────────────────────────────
    if run_stage3:
        logger.info("=" * 80)
        logger.info("Stage 3: Shoreline Extraction  [MACWE iter=%d smooth=%d]",
                    cfg.s3.MACWE_iteration, cfg.s3.MACWE_smooth)

        for save_folder, info in shores_2_extract.items():
            target_id, tidal_height, year = info["target_id"], info["tidal_height"], info["year"]
            bbox_idxs = _bbox_idxs_from_folder(save_folder)

            final_save_folder = os.path.basename(save_folder)
            for sub in _FINAL_SUBFOLDERS:
                os.makedirs(f"{save_folder}/{final_save_folder}/{sub}", exist_ok=True)

            logger.info("Extracting: %s  year=%s  tide=%s", target_id, year, tidal_height)

            inputs = [
                (base_path, save_folder, bbox_idx, final_save_folder,
                 cfg.s3.MACWE_iteration, cfg.s3.MACWE_smooth, True, random_seed,
                 cfg.s0.shore_folders)
                for bbox_idx in bbox_idxs
            ]
            with multiprocessing.Pool(min(os.cpu_count(), len(bbox_idxs), max_workers)) as pool:
                pool.starmap(s3_extract_shoreline, inputs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="NatShore — automated nation-scale shoreline extraction pipeline"
    )
    parser.add_argument(
        "--config", default="auto_bbox_config.yaml",
        help="YAML config filename inside natshore/configs/ (default: auto_bbox_config.yaml)",
    )
    parser.add_argument(
        "--stages", nargs="+", default=["1", "2A", "2B", "3"],
        choices=["1", "2A", "2B", "3"],
        metavar="{1,2A,2B,3}",
        help="Pipeline stages to run (default: all). Example: --stages 2B 3",
    )
    parser.add_argument(
        "--new-run", action="store_true",
        help="Create a new versioned output folder instead of resuming the last run",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable DEBUG-level logging",
    )
    parsed = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if parsed.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    main(parsed)

"""
Usage:
    cd natshore
    uv run --project .. python main.py --config auto_bbox_config.yaml            # all stages
    uv run --project .. python main.py --config auto_bbox_config.yaml --stages 3 # stage 3 only
    nohup uv run --project .. python -u main.py --config auto_bbox_config.yaml &> run.log &
"""
