# NatShore


NatShore is a fully automated, open-source Python framework for nation- to global-scale shoreline extraction and spatio-temporal change analysis using cross-mission satellite image. It integrates physics-based spatial unit definition, tidal-informed image selection, and a pixel-level confidence metric to deliver transparent, reproducible, and high-resolution shoreline datasets. NatShore supports applications from operational coastal monitoring and disaster impact assessment to intertidal zone reconstruction, enabling a transition from static mapping to dynamic, policy-relevant shoreline observation.
![Alt text](/images/abstractFig_NatShore.png)

### Quick start (simple usage)
- Entry point: `natshore/main.py`
- Example commands:

```bash
conda a
conda create -n natshore python=3.10
ctivate natshore


pip install uv
uv pip install 
uv pip install -r requirements.txt
# From repository root
python -m main.py --config auto_bbox_config.yaml
```

### Configuration
- Config files live in `natshore/configs/`:
  - `auto_bbox_config.yaml`
- Pass the filename via `--config` (see examples above).

### Minimal workflow (high-level)
- Stage 1: Auto-define bounding boxes and preparation.
- Stage 2A: Select best date and tidal height candidates.
- Stage 2B: Download imagery for selected dates/heights.
- Stage 3: Extract shoreline and export outputs.

<!-- ### Installation / Requirements -->
<!-- Fill in environment and dependency details (e.g., conda env or pip requirements) -->

<!-- ### Data and Outputs -->
<!-- Briefly describe expected input data layout and where outputs are saved -->

<!-- ### Reproducibility -->
<!-- Note seeds, versions, and any external services (e.g., Google Earth Engine) if applicable -->

<!-- ### Citation -->
<!-- Provide BibTeX or plain-text citation for the paper above -->

### License
- See `LICENSE` in this repository.

