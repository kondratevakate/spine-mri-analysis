"""Assemble the reader prototype from licensed local RSNA data and frozen panel scores."""

import argparse
import base64
import json
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pydicom
from skimage.feature import hog

LEVELS = ["L1/L2", "L2/L3", "L3/L4", "L4/L5", "L5/S1"]


def jpg(im, side):
    h, w = im.shape
    im = cv2.resize(
        im,
        (round(w * side / max(h, w)), round(h * side / max(h, w))),
        interpolation=cv2.INTER_AREA,
    )
    ok, data = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 77])
    assert ok
    return base64.b64encode(data).decode()


def plane(ds, sagittal=False):
    im = ds.pixel_array.astype(float)
    lo, hi = np.percentile(im, [1, 99])
    im = np.uint8(255 * np.clip((im - lo) / max(hi - lo, 1), 0, 1))
    if ds.PhotometricInterpretation == "MONOCHROME1":
        im = 255 - im
    ux, uy = np.array(ds.ImageOrientationPatient).reshape(2, 3)
    if ux[1 if sagittal else 0] < 0:
        im = np.fliplr(im)
    if uy[2] > 0 if sagittal else uy[1] < 0:
        im = np.flipud(im)
    return im


def descriptor(im):
    norm = cv2.createCLAHE(clipLimit=2, tileGridSize=(4, 4)).apply(
        cv2.resize(im, (96, 96))
    )
    v = hog(
        norm, orientations=8, pixels_per_cell=(16, 16), cells_per_block=(2, 2)
    ).astype("float32")
    return v / max(np.linalg.norm(v), 1e-8)


def series_index(folder, axis):
    rows = []
    for f in folder.glob("*.dcm"):
        ds = pydicom.dcmread(
            f,
            stop_before_pixels=True,
            specific_tags=[
                "ImagePositionPatient",
                "ImageOrientationPatient",
                "InstanceNumber",
            ],
        )
        rows.append(
            (
                float(ds.ImagePositionPatient[axis]),
                int(ds.InstanceNumber),
                f,
                np.array(ds.ImageOrientationPatient),
            )
        )
    return sorted(rows, key=lambda r: (r[0], str(r[2])))


def axial_level(points, series, folders):
    # Use bilateral same-level landmark annotations only to select the plane.
    if (
        len(points) != 2
        or points.condition.nunique() != 2
        or points.series_id.nunique() != 1
    ):
        return None, None
    sid = points.series_id.iloc[0]
    if sid not in series:
        return None, None
    if sid not in folders:
        folders[sid] = series_index(series[sid], 2)
    seq = folders[sid]
    positions = {r[1]: i for i, r in enumerate(seq)}
    if any(int(n) not in positions for n in points.instance_number):
        return None, None
    a, b = sorted(positions[int(n)] for n in points.instance_number)
    if seq[b][0] - seq[a][0] > 6 or b - a > 1:
        return None, None
    m = (a + b) // 2
    o = seq[m][3].reshape(2, 3)
    if abs(o[0, 0]) < 0.80 or abs(o[1, 1]) < 0.65 or abs(np.cross(*o)[2]) < 0.65:
        return None, None
    indices = [m]
    if 0 < m < len(seq) - 1 and all(
        0.1 < abs(seq[k][0] - seq[m][0]) <= 7
        and np.max(abs(seq[k][3] - seq[m][3])) < 0.04
        for k in (m - 1, m + 1)
    ):
        indices = [m - 1, m, m + 1]
    images = [plane(pydicom.dcmread(seq[k][2])) for k in indices]
    coords = np.array([descriptor(im) for im in images])
    return dict(
        series=sid,
        instances=[seq[k][1] for k in indices],
        images=[jpg(im, 224) for im in images],
    ), coords


def build(cache, original, payload):
    raw = original.read_text(encoding="utf8")
    if original.suffix.lower() == ".html":
        start = '<script id="dataset" type="application/json">'
        raw = raw.split(start, 1)[1].split("</script>", 1)[0]
    v = json.loads(raw)
    cached = np.load(cache / "paired-features-v1/sagittal.npz")
    idx = {s: i for i, s in enumerate(cached["ids"])}
    full, xy = cached["full"], cached["targets"]
    rows = v["q"] + v["bank"]
    nq = len(v["q"])
    series = pd.read_csv(cache / "train_series_descriptions.csv", dtype=str)
    points = pd.read_csv(
        cache / "train_label_coordinates.csv", dtype={"study_id": str, "series_id": str}
    )
    ann = points[points.condition.str.endswith("Subarticular Stenosis")].groupby(
        ["study_id", "level"]
    )
    sag = []
    features = []
    output = []
    for i, r in enumerate(rows):
        study = r["id"]
        folder = cache / "train_images" / study
        ss = series[series.study_id == study]
        axial = {
            s: folder / s
            for s in ss.loc[ss.series_description.eq("Axial T2"), "series_id"]
        }
        folders = {}
        levels = []
        feat = []
        for level in LEVELS:
            g = (study, level)
            a, f = (
                axial_level(ann.get_group(g), axial, folders)
                if g in ann.groups
                else (None, None)
            )
            levels.append(a)
            feat.append(f)
        k = idx[study]
        sag.append(descriptor(full[k]))
        if "image" in r:
            image = r["image"]
        else:
            sag_series = ss.loc[
                ss.series_description.eq("Sagittal T2/STIR"), "series_id"
            ].item()
            planes = series_index(folder / sag_series, 0)
            image = jpg(plane(pydicom.dcmread(planes[len(planes) // 2][2]), True), 288)
        p = np.array(r["p"]).mean(1)
        calls = np.where(p[:, 2] >= 0.5, 2, p[:, :2].argmax(1))
        output.append(
            dict(
                id=study,
                sag=image,
                xy=[point.round(5).tolist() if np.isfinite(point).all() else None for point in xy[k]],
                ax=levels,
                call=calls.tolist(),
                score=p.round(5).tolist(),
                ref=r["grade"],
            )
        )
        features.append(feat)
        if (i + 1) % 50 == 0:
            print(f"Prepared {i + 1}/{len(rows)} studies", flush=True)
    # Full-plane descriptors, equally weighted across three aligned axial positions.
    # Anatomical level, reference grade and fixed reference agreement are eligibility criteria.
    sg = np.array(sag)
    sgsim = sg[:nq] @ sg[nq:].T
    for level in range(5):
        good = [i for i, f in enumerate(features) if f[level] is not None]
        mats = np.zeros((len(rows), 3, len(sg[0])), np.float32)
        for i in good:
            mats[i] = features[i][level]
        axsim = sum(mats[:nq, t] @ mats[nq:, t].T for t in range(3)) / 3
        sim = 0.75 * axsim + 0.25 * sgsim
        central = 0.75 * (mats[:nq, 1] @ mats[nq:, 1].T) + 0.25 * sgsim
        available = [
            [
                j
                for j, r in enumerate(output[nq:])
                if features[nq + j][level] is not None and r["call"][level] == r["ref"][level] == g
            ]
            for g in range(3)
        ]
        stacks = [
            [j for j in group if len(features[nq + j][level]) == 3] for group in available
        ]
        for i, r in enumerate(output[:nq]):
            f = features[i][level]
            eligible = stacks if f is not None and len(f) == 3 else available
            metric = sim if eligible is stacks else central
            r.setdefault("neighbors", []).append(
                [
                    [
                        int(j)
                        for j in sorted(
                            group, key=lambda j: (-metric[i, j], output[nq + j]["id"])
                        )[:5]
                    ]
                    if f is not None
                    else []
                    for group in eligible
                ]
            )
    used = sorted(
        {
            j
            for r in output[:nq]
            for lev in r["neighbors"]
            for group in lev
            for j in group
        }
    )
    obj = dict(
        q=output[:nq],
        bank={j: output[nq + j] for j in used},
        start=v["start"],
        bankSize=len(v["bank"]),
    )
    payload.parent.mkdir(parents=True, exist_ok=True)
    result = json.dumps(obj, separators=(",", ":"))
    if payload.suffix.lower() == ".html":
        result = (
            Path(__file__)
            .with_name("reader.html")
            .read_text(encoding="utf8")
            .replace("__DATA__", result)
        )
    payload.write_text(result, encoding="utf8")
    print("Saved", payload, payload.stat().st_size, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for name in ["cache", "original", "payload"]:
        ap.add_argument(name, type=Path)
    args = ap.parse_args()
    build(args.cache, args.original, args.payload)
