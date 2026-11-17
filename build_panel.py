"""Build an offline RSNA central canal review panel from the original experiment."""
import argparse
import base64
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import pydicom
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, normalize

LEVELS = ["l1_l2", "l2_l3", "l3_l4", "l4_l5", "l5_s1"]
MODELS = ["resnet18", "whole", "sagittal", "paired"]
GRADES = ["Normal/Mild", "Moderate", "Severe"]


def encode(data):
    return base64.b64encode(data).decode("ascii")


def jpeg(im, quality):
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    return encode(buf)


def source_crops(im, centers, fov):
    """Sample the same 48 mm regions directly on the oriented source plane."""
    grid = (np.arange(128, dtype=np.float32) + .5) / 128 - .5
    result = []
    for x, y in centers:
        xx = (x + grid * 48 / fov[0]) * im.shape[1] - .5
        yy = (y + grid * 48 / fov[1]) * im.shape[0] - .5
        mx, my = np.meshgrid(xx.astype("float32"), yy.astype("float32"))
        patch = cv2.remap(im, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        result.append(jpeg(patch, 90))
    return result


def probabilities(frame, study_ids, labels):
    index = pd.MultiIndex.from_product([study_ids, LEVELS], names=["study_id", "level"])
    scores = []
    for method in MODELS:
        part = frame[frame.method.eq(method)].set_index(["study_id", "level"]).loc[index]
        assert np.array_equal(part.grade, labels.ravel())
        scores.append(part[["p_normal_mild", "p_moderate", "p_severe"]].to_numpy())
    return np.stack(scores, axis=1).reshape(len(study_ids), 5, 4, 3)


def main():
    parser = argparse.ArgumentParser()
    for name in ["cache", "source", "transfer", "output"]:
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    sys.path[:0] = [str(args.source), str(args.transfer)]
    from baseline import middle_slice
    from localize import image, geometry
    from check_transfer import encoder, extract
    torch.set_num_threads(3)
    source, run = args.source / "paired-20261116", args.source / "run-20261116"
    manifest = json.loads((run / "manifest.json").read_text())
    splits = {s: np.array(manifest[s], dtype=str) for s in ["train", "test", "validation"]}
    train = np.random.default_rng(20261117).choice(splits["train"], 256, replace=False)
    query, bank = splits["test"], splits["validation"]
    assert not (set(train) & set(query) or set(train) & set(bank) or set(query) & set(bank))
    studies = np.concatenate([train, query, bank])
    cache = np.load(args.cache / "paired-features-v1" / "sagittal.npz")
    idx = pd.Index(cache["ids"]).get_indexer(studies)
    assert min(idx) >= 0
    crops, coords, fields = (cache[k][idx] for k in ["crops", "predicted", "fields"])
    labels = pd.read_csv(args.cache / "train.csv", dtype={"study_id": str}).set_index("study_id")
    grades = labels.loc[studies, ["spinal_canal_stenosis_" + l for l in LEVELS]].to_numpy()
    assert np.isin(grades, GRADES).all()
    grades = np.array([GRADES.index(g) for g in grades.ravel()]).reshape(-1, 5)
    print("Extracting knee ConvNeXt-T embeddings", flush=True)
    model = encoder("knee", args.transfer / "weights" / "convnext_t_256.pth")
    with torch.inference_mode():
        vectors = extract(model, crops.reshape(-1, 64, 64), "knee")
    nt = len(train) * 5
    scaler = StandardScaler().fit(vectors[:nt])
    x = np.column_stack([scaler.transform(vectors), np.tile(np.eye(5), (len(studies), 1))])
    head = LogisticRegression(C=.01, max_iter=1000).fit(x[:nt], grades[:len(train)].ravel())
    knee = head.predict_proba(x[nt:]).reshape(-1, 5, 1, 3)
    read = lambda path: pd.read_csv(path, dtype={"study_id": str})
    val = pd.concat([read(run / "validation.csv")] +
                    [read(source / m / "validation.csv") for m in MODELS[1:]])
    grades, coords, fields, crops = (a[len(train):] for a in [grades, coords, fields, crops])
    nq = len(query)
    lumbar = np.concatenate([probabilities(read(source / "paired-test.csv"), query, grades[:nq]),
                             probabilities(val, bank, grades[nq:])])
    pred = np.concatenate([lumbar, knee], axis=2)
    assert np.isfinite(pred).all() and np.allclose(pred.sum(-1), 1, atol=1e-5)
    vectors = normalize(scaler.transform(vectors[nt:])).reshape(len(pred), 5, -1)
    similarity = np.stack([vectors[:nq, l] @ vectors[nq:, l].T for l in range(5)], axis=1)
    series = pd.read_csv(args.cache / "train_series_descriptions.csv", dtype=str)
    series = series[series.series_description.eq("Sagittal T2/STIR")].set_index("study_id")
    mean = pred[:nq, 3].mean(1)
    candidates = np.flatnonzero((grades[:nq, 3] == 2) & (mean[:, 1] > mean[:, 0]))
    initial = int(candidates[np.argmin(abs(mean[candidates, 2] - .45))])
    print("Assembling sagittal images", flush=True)
    rows = []
    for i, sid in enumerate(np.concatenate([query, bank])):
        record = dict(id=sid, grade=grades[i].tolist(), p=pred[i].round(7).tolist())
        folder = args.cache / "train_images" / sid / series.at[sid, "series_id"]
        ds = pydicom.dcmread(middle_slice(folder))
        im = image(ds)
        _, directions, _, _ = geometry(ds)
        if directions[0, 1] < 0:
            im = np.fliplr(im)
        if directions[1, 2] > 0:
            im = np.flipud(im)
        record["crops"] = source_crops(im, coords[i], fields[i])
        if i < nq:
            height, width = np.rint(480 * fields[i][::-1] / max(fields[i])).astype(int)
            im = cv2.resize(im, (width, height), interpolation=cv2.INTER_AREA)
            record.update(image=jpeg(im, 86), dims=[int(width), int(height)], xy=coords[i].round(6).tolist(),
                          fov=fields[i].round(3).tolist(),
                          sim=encode(np.rint(similarity[i]*32767).astype("<i2").tobytes()))
        rows.append(record)
    payload = dict(q=rows[:nq], bank=rows[nq:], start=initial)
    work = Path(__file__).with_name("work")
    work.mkdir(exist_ok=True)
    raw = json.dumps(payload, separators=(",", ":"))
    (work / "panel-data.json").write_text(raw, encoding="utf8")
    template = Path(__file__).with_name("panel.html").read_text(encoding="utf8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(template.replace("__PAYLOAD__", raw),
                           encoding="utf8")
    print(args.output, args.output.stat().st_size, query[initial], mean[initial], flush=True)


if __name__ == "__main__":
    main()
