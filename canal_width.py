"""Relative dural-sac width on sagittal T2: a pathology descriptor independent of patient size.

For each lumbar disc named by disc_levels.py (counted from the sacrum), on the sagittal slice
through the disc centroid:
  1. find the posterior edge of the disc at its craniocaudal centre;
  2. walk posteriorly and measure the run of bright CSF (above half the patient's CSF reference
     intensity) that starts within 4 mm of the disc edge: absolute width in mm;
  3. repeat at the mid-height of each vertebral body, where degenerative narrowing is rare;
  4. relative width = level width / median mid-vertebral width of the same patient.

Severe central stenosis effaces CSF, so relative width should fall towards zero. The
measurement is a hypothesis-level proxy (no reference masks); the QC sheet shows every line.

Usage: python canal_width.py DATA DISC_LEVELS_DIR OUTDIR
"""

import argparse
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
from scipy import ndimage

LEVELS = ["L1/L2", "L2/L3", "L3/L4", "L4/L5", "L5/S1"]
GRADES = {"Normal/Mild": 0, "Moderate": 1, "Severe": 2}
THRESHOLD = 0.6  # fraction of the patient CSF reference; 0.5 included bright epidural fat on QC


def axes(affine):
    """Return (ap_axis, ap_sign, si_axis, si_sign) in voxel index space; +sign = posterior / inferior."""
    d = affine[:3, :3]
    ap = int(np.argmax(np.abs(d[1])))  # RAS y = anterior
    si = int(np.argmax(np.abs(d[2])))  # RAS z = superior
    return ap, -int(np.sign(d[1, ap])), si, -int(np.sign(d[2, si]))


def components(folder):
    disc = nib.load(folder / "segmentations" / "intervertebral_discs.nii.gz")
    aff = disc.affine
    mask = np.asarray(disc.dataobj) > 0
    sac = np.asarray(nib.load(folder / "segmentations" / "sacrum.nii.gz").dataobj) > 0
    lab, n = ndimage.label(mask)
    vox = float(abs(np.linalg.det(aff[:3, :3])))
    comps = []
    for k in range(1, n + 1):
        idx = np.argwhere(lab == k)
        if len(idx) * vox < 200:
            continue
        comps.append((float((aff[:3, :3] @ idx.mean(0) + aff[:3, 3])[2]), idx.mean(0), lab == k))
    comps.sort(key=lambda c: c[0])
    merged = []  # merge disc fragments < 8 mm apart along SI, as in disc_levels.centroids
    for c in comps:
        if merged and abs(c[0] - merged[-1][0]) < 8:
            merged[-1] = (merged[-1][0], merged[-1][1], merged[-1][2] | c[2])
        else:
            merged.append(c)
    comps = merged
    top = None
    if sac.any():
        top = float((aff[:3, :3] @ np.argwhere(sac).T + aff[:3, 3:4])[2].max())
    above = [c for c in comps if top is None or c[0] > top - 15]
    return {LEVELS[4 - j]: c for j, c in enumerate(above[:5])}, aff


def walk(sl2, p, d, mm, length_mm=25.0, width_mm=1.0):
    """Sample `sl2` (indexed [ap, si]) from point p along unit mm-direction d, 0.5 mm steps,
    averaging over +-width_mm perpendicular offsets. Returns intensities and voxel points."""
    from scipy.ndimage import map_coordinates

    n = int(length_mm / 0.5)
    t = np.arange(n) * 0.5
    perp = np.array([-d[1], d[0]])
    offs = np.arange(-width_mm, width_mm + 1e-6, 0.5)
    pts_mm = p * mm + t[:, None] * d
    vals = []
    for o in offs:
        q = (pts_mm + o * perp) / mm
        vals.append(map_coordinates(sl2, q.T, order=1, mode="nearest"))
    return np.mean(vals, axis=0), pts_mm / mm


def exit_point(mask2, p, d, mm, max_mm=60.0):
    """First point along d (mm units) where the mask ends, starting inside it."""
    for t in np.arange(0, max_mm, 0.25):
        q = np.round((p * mm + t * d) / mm).astype(int)
        if not (0 <= q[0] < mask2.shape[0] and 0 <= q[1] < mask2.shape[1]) or not mask2[q[0], q[1]]:
            return (p * mm + t * d) / mm
    return None


def run_width(prof, thr, gap_mm=6.0, step_mm=0.5):
    above = prof >= thr
    first = np.flatnonzero(above[: int(gap_mm / step_mm) + 1])
    if len(first) == 0:
        return 0.0, 0, 0
    a = b = first[0]
    while b + 1 < len(above) and above[b + 1]:
        b += 1
    return (b - a + 1) * step_mm, a, b


def to_ap_si(arr2, rem, ap_ax):
    """Return a 2-D slice indexed [ap, si]."""
    return arr2 if rem.index(ap_ax) == 0 else arr2.T


def measure(folder):
    """Measure along the disc plane (posterior direction of the disc's long axis), which follows
    lordosis at L5/S1; reference at mid vertebral body along the mean adjacent disc axis."""
    named, aff = components(folder)
    vol = np.asarray(nib.load(folder / "sagittal.nii.gz").dataobj).astype(np.float32)
    vert = np.asarray(nib.load(folder / "segmentations" / "vertebrae.nii.gz").dataobj) > 0
    ap_ax, ap_sign, si_ax, _ = axes(aff)
    lr_ax = 3 - ap_ax - si_ax
    rem = [x for x in range(3) if x != lr_ax]
    vs = np.linalg.norm(aff[:3, :3], axis=0)
    mm = np.array([vs[ap_ax], vs[si_ax]])
    discs = {}
    for lv, (_, c, comp) in named.items():
        k = int(round(c[lr_ax]))
        cm = to_ap_si(np.take(comp, k, axis=lr_ax), rem, ap_ax)
        if cm.sum() < 5:
            continue
        idx = np.argwhere(cm).astype(float)
        cen = idx.mean(0)
        x = (idx - cen) * mm
        w, v = np.linalg.eigh(x.T @ x)
        d = v[:, np.argmax(w)]
        if np.sign(d[0]) != ap_sign:
            d = -d
        edge = exit_point(cm, cen, d, mm)
        if edge is None:
            continue
        discs[lv] = dict(k=k, cen=cen, d=d, edge=edge)
    out, lines = {}, []
    if not discs:
        return out, lines
    profs = {}
    for lv, q in discs.items():
        sl = to_ap_si(np.take(vol, q["k"], axis=lr_ax), rem, ap_ax)
        profs[lv] = walk(sl, q["edge"], q["d"], mm)
    refs = []
    order = [lv for lv in LEVELS if lv in discs]
    for u, w2 in zip(order[:-1], order[1:]):
        a, b = discs[u], discs[w2]
        k = int(round((a["k"] + b["k"]) / 2))
        cen = (a["cen"] + b["cen"]) / 2
        d = a["d"] + b["d"]
        d = d / np.linalg.norm(d)
        vm = to_ap_si(np.take(vert, k, axis=lr_ax), rem, ap_ax)
        qi = np.round(cen).astype(int)
        if not vm[qi[0], qi[1]]:
            continue  # body centre not inside the vertebra mask: skip this reference
        edge = exit_point(vm, cen, d, mm)
        if edge is None:
            continue
        sl = to_ap_si(np.take(vol, k, axis=lr_ax), rem, ap_ax)
        refs.append((k, edge, d, walk(sl, edge, d, mm)))
    pool = np.concatenate([p[0] for p in profs.values()] + [r[3][0] for r in refs])
    thr = THRESHOLD * np.nanpercentile(pool, 90)
    ref_w = []
    for k, edge, d, (pr, pts) in refs:
        w, i0, i1 = run_width(pr, thr)
        ref_w.append(w)
        lines.append(("ref", k, pts[i0], pts[i1]))
    base = float(np.median(ref_w)) if ref_w else np.nan
    for lv, (pr, pts) in profs.items():
        w, i0, i1 = run_width(pr, thr)
        out[lv] = dict(width_mm=w, rel_width=w / base if base and base > 0 else np.nan,
                       slice=discs[lv]["k"], references=len(ref_w))
        lines.append((lv, discs[lv]["k"], pts[i0], pts[i1]))
    return out, lines


def qc(folder, lines, res, path):
    from PIL import Image, ImageDraw

    img = nib.load(folder / "sagittal.nii.gz")
    vol = np.asarray(img.dataobj).astype(np.float32)
    ap_ax, ap_sign, si_ax, _ = axes(img.affine)
    lr_ax = 3 - ap_ax - si_ax
    rem = [x for x in range(3) if x != lr_ax]
    k = int(np.median([ln[1] for ln in lines if ln[0] != "ref"]))
    sl = to_ap_si(np.take(vol, k, axis=lr_ax), rem, ap_ax).T  # rows = SI, cols = AP
    lo, hi = np.percentile(sl, [1, 99])
    im = Image.fromarray(np.uint8(np.clip((sl - lo) / (hi - lo + 1e-6), 0, 1) * 255)).convert("RGB")
    sx, sy = 360 / im.width, 360 / im.height
    im = im.resize((360, 360))
    d = ImageDraw.Draw(im)
    for name, _, p0, p1 in lines:
        col = "#9fb0bf" if name == "ref" else "#3fe0d0"
        d.line((p0[0] * sx, p0[1] * sy, p1[0] * sx, p1[1] * sy), fill=col, width=3)
        if name != "ref":
            r = res.get(name, {})
            d.text((p1[0] * sx + 4, p1[1] * sy - 6), f"{name} {r.get('grade', '?')} {r.get('rel_width', np.nan):.2f}", fill="#ffd23f")
    d.text((4, 4), folder.name, fill="white")
    im.save(path)


def main():
    ap = argparse.ArgumentParser()
    for k in ("data", "levels", "out"):
        ap.add_argument(k, type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    table = pd.read_csv(a.data / "train.csv", dtype={"study_id": str}).set_index("study_id")
    rows, tiles = [], []
    for folder in sorted(p for p in a.levels.iterdir() if (p / "segmentations" / "intervertebral_discs.nii.gz").exists()):
        try:
            res, lines = measure(folder)
        except Exception as err:  # recorded per study, never silently dropped
            rows.append(dict(study_id=folder.name, level=None, error=repr(err)))
            print("failed", folder.name, repr(err), flush=True)
            continue
        for lv, r in res.items():
            g = table.at[folder.name, "spinal_canal_stenosis_" + lv.lower().replace("/", "_")]
            r["grade"] = GRADES.get(g, -1) if isinstance(g, str) else -1
            rows.append(dict(study_id=folder.name, level=lv, **r))
        p = a.out / f"qc-{folder.name}.png"
        qc(folder, lines, res, p)
        tiles.append(p)
    df = pd.DataFrame(rows)
    df.to_csv(a.out / "canal-width.csv", index=False)
    print("studies", df.study_id.nunique(), "levels", int(df.level.notna().sum()), flush=True)
    sheet(tiles[:12], a.out / "canal-width-qc.png")
    print(json.dumps(df[df.level.notna()].groupby("grade")[["width_mm", "rel_width"]].median().round(2).to_dict()))


def sheet(tiles, path):
    from PIL import Image

    if not tiles:
        raise SystemExit("No measured study")
    ims = [Image.open(t) for t in tiles]
    s = Image.new("RGB", (360 * 4, 360 * ((len(ims) + 3) // 4)), (14, 22, 30))
    for i, im in enumerate(ims):
        s.paste(im, (360 * (i % 4), 360 * (i // 4)))
    s.save(path)
    print("saved", path)


if __name__ == "__main__":
    main()
