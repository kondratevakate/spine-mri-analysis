"""Visual QC sheet: automatic versus reference-centred crops on the mid-sagittal image.

Rows: the demo study 1269700501 and the test levels with the largest displacement, plus a
random sample. Columns: full image with both centres, automatic crop, reference crop.

Usage: python relocalize_qc.py DATA ORIGINAL_PROJECT RELOCALIZED_DIR
"""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

LEVELS = ["L1/L2", "L2/L3", "L3/L4", "L4/L5", "L5/S1"]


def main():
    ap = argparse.ArgumentParser()
    for k in ("data", "original", "out"):
        ap.add_argument(k, type=Path)
    a = ap.parse_args()
    sag = np.load(a.data / "paired-features-v1" / "sagittal.npz")
    ids, fields = sag["ids"], sag["fields"]
    images = np.load(a.out / "images224.npy")
    ref = np.load(a.out / "reference-crops.npz")["crops"]
    test = set(json.loads((a.original / "run-20261116" / "manifest.json").read_text())["test"])
    d = np.linalg.norm((sag["predicted"] - sag["targets"]) * fields[:, None, :], axis=2)
    cand = [(d[i, j], i, j) for i in range(len(ids)) if ids[i] in test for j in range(5) if np.isfinite(d[i, j]) and (sag["targets"][i, j] > 0.03).all()]
    cand.sort(reverse=True)
    demo = int(np.flatnonzero(ids == "1269700501")[0])
    rng = np.random.default_rng(20261118)
    picks = [(d[demo, 3], demo, 3)] + cand[:4] + [cand[k] for k in rng.choice(len(cand), 3, replace=False)]
    W, H = 3 * 224 + 40, 30 + len(picks) * 234
    sheet = Image.new("RGB", (W, H), (16, 24, 32))
    draw = ImageDraw.Draw(sheet)
    draw.text((10, 8), "Full sagittal (yellow=automatic, cyan=RSNA reference) | automatic crop | reference crop", fill="white")
    for r, (dist, i, j) in enumerate(picks):
        y = 30 + r * 234
        full = Image.fromarray(images[i]).convert("RGB")
        g = ImageDraw.Draw(full)
        for centre, colour in ((sag["predicted"][i, j], "#ffd23f"), (sag["targets"][i, j], "#3fe0d0")):
            cx, cy = centre * 224
            half = 48 / fields[i] * 224 / 2
            g.rectangle((cx - half[0], cy - half[1], cx + half[0], cy + half[1]), outline=colour, width=2)
        sheet.paste(full, (10, y))
        sheet.paste(Image.fromarray(sag["crops"][i, j]).resize((224, 224)).convert("RGB"), (244, y))
        sheet.paste(Image.fromarray(ref[i, j]).resize((224, 224)).convert("RGB"), (478, y))
        draw.text((14, y + 4), f"{ids[i]} {LEVELS[j]}  {dist:.1f} mm", fill="#ffffff")
    sheet.save(a.out / "relocalize-qc.png")
    print("saved", a.out / "relocalize-qc.png", "rows", len(picks))


if __name__ == "__main__":
    main()
