"""Smoke test: do TotalSegmentator disc masks name lumbar levels better than the old localizer?

Two subcommands, because TotalSegmentator runs in WSL while DICOM reading runs on Windows:

  python disc_levels.py prepare DATA OUTDIR STUDY...      (Windows: volumes + RSNA landmarks)
  python disc_levels.py segment OUTDIR [STUDY...]         (WSL: total_mr discs + sacrum)
  python disc_levels.py score DATA OUTDIR                  (Windows: level assignment + QC sheet)

Levels are counted from the sacrum upwards: the lowest disc component above the sacrum is
L5/S1. Transitional anatomy breaks this rule by design, and the score exposes it.

Level assignment is correct when the point for level j lies closer, along the superior-inferior
axis, to the RSNA landmark of level j than to any other RSNA landmark of that study. The same
rule scores the old automatic localizer, so both use one definition.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

LEVELS = ["L1/L2", "L2/L3", "L3/L4", "L4/L5", "L5/S1"]


def prepare(a):
    from prepare_volume import build

    for study in a.studies:
        try:
            build(a.data, study, a.out / study)
        except Exception as err:  # recorded, not hidden: irregular series are a finding
            (a.out / study).mkdir(parents=True, exist_ok=True)
            (a.out / study / "prepare-error.txt").write_text(repr(err))
            print("prepare failed", study, repr(err), flush=True)


def segment(a):
    root = Path(__file__).resolve().parent
    os.environ["TOTALSEG_HOME_DIR"] = str(root / "work" / "totalseg-models")
    os.environ["nnUNet_compile"] = "false"
    import torch
    from totalsegmentator.config import set_config_key, setup_totalseg
    from totalsegmentator.python_api import totalsegmentator

    setup_totalseg()
    set_config_key("send_usage_stats", False)
    torch.set_num_threads(4)
    todo = [
        p for p in sorted(a.out.iterdir())
        if (p / "sagittal.nii.gz").exists()
        and (not a.studies or p.name in a.studies)
        and not (p / "segmentations" / "intervertebral_discs.nii.gz").exists()
    ]
    began = time.monotonic()
    for done, folder in enumerate(todo):
        start = time.monotonic()
        if done:
            eta = (start - began) / done * (len(todo) - done) / 60
            print(f"progress {done}/{len(todo)}, ETA {eta:.0f} min", flush=True)
        try:
            run_one(totalsegmentator, folder)
        except Exception as err:  # one bad series must not stop the cohort; recorded per study
            (folder / "segment-error.txt").write_text(repr(err))
            print("segment failed", folder.name, repr(err), flush=True)
            continue
        print("segmented", folder.name, round(time.monotonic() - start), "s", flush=True)
    print(f"segment finished {len(todo)} studies in {(time.monotonic() - began) / 60:.0f} min", flush=True)


def run_one(totalsegmentator, folder):
    totalsegmentator(
        folder / "sagittal.nii.gz", folder / "segmentations", task="total_mr", fast=True,
        device="cpu", roi_subset=["vertebrae", "intervertebral_discs", "sacrum"],
        nr_thr_resamp=1, nr_thr_saving=1, quiet=True,
    )


def centroids(folder):
    import nibabel as nib
    from scipy import ndimage

    disc = nib.load(folder / "segmentations" / "intervertebral_discs.nii.gz")
    sacrum = np.asarray(nib.load(folder / "segmentations" / "sacrum.nii.gz").dataobj) > 0
    mask = np.asarray(disc.dataobj) > 0
    labels, n = ndimage.label(mask)
    affine = disc.affine
    voxel = float(np.prod(np.abs(np.linalg.det(affine[:3, :3]))))
    comps = []
    for k in range(1, n + 1):
        idx = np.argwhere(labels == k)
        if len(idx) * voxel < 200:  # drop fragments below 0.2 ml
            continue
        ras = affine[:3, :3] @ idx.mean(0) + affine[:3, 3]
        comps.append(ras)
    comps.sort(key=lambda r: r[2])  # inferior to superior
    sac_top = None
    if sacrum.any():
        idx = np.argwhere(sacrum)
        sac_top = float((affine[:3, :3] @ idx.T + affine[:3, 3:4])[2].max())
    above = [c for c in comps if sac_top is None or c[2] > sac_top - 15]
    named = {}
    for j, c in enumerate(above[:5]):
        named[LEVELS[4 - j]] = c
    return named, len(comps), sac_top


def assign(points, refs):
    """Correct if point j is SI-nearest to reference j among all references."""
    out = {}
    for lv, p in points.items():
        if lv not in refs:
            continue
        nearest = min(refs, key=lambda r: abs(refs[r][2] - p[2]))
        out[lv] = dict(ok=nearest == lv, si_mm=float(p[2] - refs[lv][2]))
    return out


def score(a):
    sag = np.load(a.data / "paired-features-v1" / "sagittal.npz")
    ids = list(sag["ids"])
    rows = []
    for folder in sorted(p for p in a.out.iterdir() if p.is_dir()):
        if not (folder / "segmentations" / "intervertebral_discs.nii.gz").exists():
            continue  # scored set = segmented studies only; the sample is chosen at segment time
        geo = folder / "geometry.json"
        if not geo.exists():
            rows.append(dict(study=folder.name, status="prepare failed"))
            continue
        g = json.loads(geo.read_text())
        refs = {p["level"]: np.array(p["ras"]) for p in g["landmarks"]}
        refs = {k: v for k, v in refs.items() if np.isfinite(v).all()}
        world = sag["world"][ids.index(folder.name)] * [-1, -1, 1]  # LPS -> RAS
        auto = {LEVELS[j]: world[j] for j in range(5)}
        if not (folder / "segmentations" / "intervertebral_discs.nii.gz").exists():
            rows.append(dict(study=folder.name, status="not segmented"))
            continue
        disc, n, sac = centroids(folder)
        rows.append(dict(
            study=folder.name, status="ok", disc_components=n, sacrum_found=sac is not None,
            auto=assign(auto, refs), discs=assign(disc, refs),
        ))
    (a.out / "disc-levels.json").write_text(json.dumps(rows, indent=2))
    for name in ("auto", "discs"):
        ok = [v["ok"] for r in rows if r.get("status") == "ok" for v in r[name].values()]
        si = [abs(v["si_mm"]) for r in rows if r.get("status") == "ok" for v in r[name].values()]
        print(f"{name}: level correct {sum(ok)}/{len(ok)}, median |SI| {np.median(si):.1f} mm", flush=True)
    for r in rows:
        if r.get("status") != "ok":
            print(r)
            continue
        print(r["study"], "components", r["disc_components"], "sacrum", r["sacrum_found"],
              "auto", "".join("+" if v["ok"] else "-" for v in r["auto"].values()),
              "discs", "".join("+" if v["ok"] else "-" for v in r["discs"].values()))
    qc_sheet(a, rows)


def qc_sheet(a, rows):
    import nibabel as nib
    from PIL import Image, ImageDraw

    tiles = []
    for r in rows:
        if r.get("status") != "ok":
            continue
        folder = a.out / r["study"]
        img = nib.load(folder / "sagittal.nii.gz")
        vol = np.asarray(img.dataobj)
        g = json.loads((folder / "geometry.json").read_text())
        k = g["middle_index"]
        disc = np.asarray(nib.load(folder / "segmentations" / "intervertebral_discs.nii.gz").dataobj)[:, :, k] > 0
        sl = vol[:, :, k].T
        lo, hi = np.percentile(sl, [1, 99])
        rgb = np.repeat(np.uint8(np.clip((sl - lo) / (hi - lo + 1e-6), 0, 1) * 255)[..., None], 3, 2)
        rgb[disc.T] = (0.5 * rgb[disc.T] + [0, 110, 80]).astype(np.uint8)
        tile = Image.fromarray(rgb).resize((360, 360))
        d = ImageDraw.Draw(tile)
        inv = np.linalg.inv(img.affine)
        named, _, _ = centroids(folder)
        sx, sy = 360 / sl.shape[1], 360 / sl.shape[0]
        for lv, c in named.items():
            i, j, _ = inv[:3, :3] @ c + inv[:3, 3]
            d.text((i * sx + 6, j * sy - 6), lv, fill="#3fe0d0")
            d.ellipse((i * sx - 3, j * sy - 3, i * sx + 3, j * sy + 3), fill="#3fe0d0")
        for p in g["landmarks"]:
            i, j, _ = inv[:3, :3] @ np.array(p["ras"]) + inv[:3, 3]
            d.ellipse((i * sx - 4, j * sy - 4, i * sx + 4, j * sy + 4), outline="#ff705f", width=2)
        ok = "".join("+" if v["ok"] else "-" for v in r["discs"].values())
        d.text((6, 6), f"{r['study']}  discs {ok}", fill="white")
        tiles.append(tile)
    if not tiles:
        raise SystemExit("No segmented study to show: check the segment step log")
    sheet = Image.new("RGB", (360 * min(3, len(tiles)), 360 * ((len(tiles) + 2) // 3)), (14, 22, 30))
    for n, t in enumerate(tiles):
        sheet.paste(t, (360 * (n % 3), 360 * (n // 3)))
    sheet.save(a.out / "disc-levels-qc.png")
    print("saved", a.out / "disc-levels-qc.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("data", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("studies", nargs="+")
    s = sub.add_parser("segment")
    s.add_argument("out", type=Path)
    s.add_argument("studies", nargs="*", help="limit to these study IDs (default: all prepared)")
    c = sub.add_parser("score")
    c.add_argument("data", type=Path)
    c.add_argument("out", type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    {"prepare": prepare, "segment": segment, "score": score}[a.cmd](a)
    sys.exit(0)
