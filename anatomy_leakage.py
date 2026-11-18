"""Does case retrieval find the same pathology, or the same scanner and patient?

For every test level (query) we retrieve the k nearest same-level crops from other patients
(train + validation bank) and measure:

  pathology: share of neighbours with the query's RSNA grade, averaged per grade so the
             90% normal/mild majority does not dominate; chance = bank grade prevalence.
  scanner:   RSNA anonymisation removed manufacturer and field strength, so acquisition is proxied
             by matrix size, pixel-spacing bin, slice thickness and their combination (protocol);
             share of neighbours with the query's value; chance = bank prevalence of that value.
  patient:   for test patients with both a moderate/severe and a normal/mild level, whether the
             diseased level is closer to its own patient's normal levels than to its 5 nearest
             same-grade levels of other patients (identity beats pathology).

Feature sets: raw crop pixels, crop HOG, whole sagittal image, and crop HOG minus the mean HOG
of the same patient's five levels (label-free self-normalisation). Crops are the 48 mm
RSNA-landmark crops from relocalize.py, so localisation error does not confound the test.

Usage: python anatomy_leakage.py DATA ORIGINAL_PROJECT RELOCALIZED_DIR OUTDIR
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom
from skimage.feature import hog

GRADES = {"Normal/Mild": 0, "Moderate": 1, "Severe": 2}
LEVELS = ["l1_l2", "l2_l3", "l3_l4", "l4_l5", "l5_s1"]
K = 5


def scanner_table(data, ids, out):
    cache = out / "scanner.csv"
    if cache.exists():
        return pd.read_csv(cache, dtype={"study_id": str}).set_index("study_id").loc[ids]
    series = pd.read_csv(data / "train_series_descriptions.csv", dtype=str)
    series = series[series.series_description.eq("Sagittal T2/STIR")].set_index("study_id").series_id
    rows = []
    for k, s in enumerate(ids):
        f = next((data / "train_images" / s / series.loc[s]).glob("*.dcm"))
        d = pydicom.dcmread(f, stop_before_pixels=True)
        rows.append(dict(
            study_id=s,
            matrix=f"{d.Rows}x{d.Columns}",
            pixel_mm=float(d.PixelSpacing[0]),
            thickness_mm=float(getattr(d, "SliceThickness", np.nan) or np.nan),
        ))
        if (k + 1) % 400 == 0:
            print("headers", k + 1, flush=True)
    t = pd.DataFrame(rows)
    t.to_csv(cache, index=False)
    return t.set_index("study_id").loc[ids]


def features(crops, full):
    n = len(crops)
    raw = crops.reshape(n, 5, -1).astype(np.float32) / 255
    h = np.array([[hog(crops[i, j], orientations=8, pixels_per_cell=(8, 8), cells_per_block=(2, 2))
                   for j in range(5)] for i in range(n)], np.float32)
    whole = np.repeat((full.reshape(n, 1, -1).astype(np.float32) / 255), 5, axis=1)
    resid = h - h.mean(axis=1, keepdims=True)
    return {"crop pixels": raw, "crop HOG": h, "whole sagittal image": whole, "crop HOG minus own-patient mean": resid}


def unit(x):
    x = x - x.mean(axis=0, keepdims=True)
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-8)


def main():
    ap = argparse.ArgumentParser()
    for k in ("data", "original", "relocalized", "out"):
        ap.add_argument(k, type=Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    sag = np.load(a.data / "paired-features-v1" / "sagittal.npz")
    ids = sag["ids"]
    crops = np.load(a.relocalized / "reference-crops.npz")["crops"]
    targets = sag["targets"]
    valid = np.isfinite(targets).all(2) & (targets > 0.03).all(2) & (targets < 0.97).all(2)
    m = json.loads((a.original / "run-20261116" / "manifest.json").read_text())
    table = pd.read_csv(a.data / "train.csv", dtype={"study_id": str}).set_index("study_id")
    grade = table.loc[ids, ["spinal_canal_stenosis_" + lv for lv in LEVELS]].apply(lambda v: v.map(GRADES)).to_numpy()
    grade = np.where(np.isnan(grade), -1, grade).astype(int)
    scan = scanner_table(a.data, list(ids), a.out)
    scan["pixel_bin"] = pd.cut(scan.pixel_mm, [0, 0.45, 0.6, 0.8, 5], labels=False)
    scan["thickness"] = scan.thickness_mm.round(1)
    scan["protocol"] = scan.matrix + "/" + scan.pixel_bin.astype(str) + "/" + scan.thickness.astype(str)
    q = np.isin(ids, m["test"])
    b = np.isin(ids, m["train"] + m["validation"])
    print("matrices", scan.matrix.nunique(), "protocols", scan.protocol.nunique(),
          "largest protocol share", round(scan.protocol.value_counts(normalize=True).iloc[0], 3), flush=True)

    feats = features(crops, sag["full"])
    rows, examples = [], {}
    for name, f in feats.items():
        res = {g: [] for g in range(3)}
        same = {"matrix": [], "pixel_bin": [], "thickness": [], "protocol": []}
        chance = {k: [] for k in same}
        patient_wins, patient_total = 0, 0
        for j in range(5):
            qi = np.flatnonzero(q & valid[:, j] & (grade[:, j] >= 0))
            bi = np.flatnonzero(b & valid[:, j] & (grade[:, j] >= 0))
            fq, fb = unit(np.concatenate([f[qi, j], f[bi, j]]))[: len(qi)], unit(np.concatenate([f[qi, j], f[bi, j]]))[len(qi):]
            sim = fq @ fb.T
            nn = np.argsort(-sim, axis=1)[:, :K]
            for r, i in enumerate(qi):
                nb = bi[nn[r]]
                res[grade[i, j]].append(np.mean(grade[nb, j] == grade[i, j]))
                for key in same:
                    v = scan[key].iloc[i]
                    same[key].append(np.mean(scan[key].iloc[nb].to_numpy() == v))
                    chance[key].append(np.mean(scan[key].iloc[bi].to_numpy() == v))
                if name not in examples and grade[i, j] == 2 and j == 3:
                    examples[name] = (i, nb)
        # patient identity test on all levels jointly
        allf = unit(f.reshape(-1, f.shape[-1])).reshape(f.shape)
        for i in np.flatnonzero(q):
            sick = [j for j in range(5) if valid[i, j] and grade[i, j] >= 1]
            well = [j for j in range(5) if valid[i, j] and grade[i, j] == 0]
            if not sick or not well:
                continue
            for j in sick:
                own = max(float(allf[i, j] @ allf[i, w]) for w in well)
                bi = np.flatnonzero(b & valid[:, j] & (grade[:, j] == grade[i, j]))
                other = np.sort(allf[bi, j] @ allf[i, j])[-K:].mean()
                patient_total += 1
                patient_wins += own > other
        prev = {g: float(np.mean(grade[b] == g)) for g in range(3)}
        rows.append(dict(
            features=name,
            same_grade_normal=float(np.mean(res[0])), same_grade_moderate=float(np.mean(res[1])),
            same_grade_severe=float(np.mean(res[2])),
            chance_moderate=prev[1], chance_severe=prev[2],
            **{f"same_{k}": float(np.mean(v)) for k, v in same.items()},
            **{f"chance_{k}": float(np.mean(v)) for k, v in chance.items()},
            # whole image is identical for all five levels of a patient: the test does not apply
            own_patient_closer=None if name == "whole sagittal image" else patient_wins / max(patient_total, 1),
            patient_pairs=patient_total,
        ))
        print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rows[-1].items()}), flush=True)
    pd.DataFrame(rows).to_csv(a.out / "anatomy-leakage.csv", index=False)
    sheet(a, crops, ids, grade, scan, examples)


def sheet(a, crops, ids, grade, scan, examples):
    from PIL import Image, ImageDraw

    names = list(examples)
    W, H = 6 * 150 + 260, len(names) * 170 + 30
    im = Image.new("RGB", (W, H), (14, 22, 30))
    d = ImageDraw.Draw(im)
    d.text((10, 8), "L4/L5 severe query (left) and its 5 nearest neighbours: RSNA grade / matrix / pixel mm", fill="white")
    lab = ["N", "M", "S"]
    for r, name in enumerate(names):
        i, nb = examples[name]
        y = 30 + r * 170
        d.text((10, y + 60), name, fill="#9fb0bf")
        for c, s in enumerate([i, *nb]):
            x = 260 + c * 150
            im.paste(Image.fromarray(crops[s, 3]).resize((140, 140)).convert("RGB"), (x, y))
            meta = scan.iloc[s]
            d.text((x, y + 142), f"{lab[grade[s, 3]]} {meta.matrix} {meta.pixel_mm:.2f}", fill="#ffd23f" if c == 0 else "white")
    im.save(a.out / "anatomy-leakage-examples.png")
    print("saved", a.out / "anatomy-leakage-examples.png")


if __name__ == "__main__":
    main()
