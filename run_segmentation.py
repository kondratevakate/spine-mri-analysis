"""Run a bounded single-study CPU TotalSegmentator MR feasibility experiment."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["TOTALSEG_HOME_DIR"] = str(ROOT / "work" / "totalseg-models")
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["OPENBLAS_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["nnUNet_compile"] = "false"


if __name__ == "__main__":
    import time
    import torch
    from totalsegmentator.config import setup_totalseg, set_config_key

    setup_totalseg()
    set_config_key("send_usage_stats", False)
    from totalsegmentator.python_api import totalsegmentator

    torch.set_num_threads(2)
    base = ROOT / "work" / "volume-1269700501"
    start = time.monotonic()
    print(
        "Starting TotalSegmentator total_mr 3 mm, CPU, 2 threads, one study", flush=True
    )
    totalsegmentator(
        base / "sagittal.nii.gz",
        base / "segmentations",
        task="total_mr",
        fast=True,
        device="cpu",
        roi_subset=["vertebrae", "intervertebral_discs", "sacrum"],
        nr_thr_resamp=1,
        nr_thr_saving=1,
        quiet=False,
        verbose=False,
    )
    print("Completed seconds", round(time.monotonic() - start, 1), flush=True)
