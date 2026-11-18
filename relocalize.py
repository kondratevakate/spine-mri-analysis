"""Re-evaluate the sagittal crop classifier with reference-centred crops.

The original classifier was trained and tested on 48 mm crops centred on an automatic
kernel-regression localizer. The 18 November marker audit measured a median 7.75 mm and up to
34 mm displacement against RSNA landmarks. This script separates localization error from
grading error:

  A. original weights, automatic crops    (reproduces the earlier result)
  B. original weights, reference crops    (train/test localization mismatch)
  C. retrained on reference crops, reference crops   (oracle-localization upper bound)
  D. retrained on reference crops, automatic crops   (what a deployed model would see)
  E. retrained on automatic crops with the same loop   (training-loop control for C)

Every arm freezes its severe threshold on validation at a 5% false-positive cap, as in
paired_evaluate.py. Levels without a reference landmark are excluded from all arms alike.

Usage: python relocalize.py DATA ORIGINAL_PROJECT OUTPUT_DIR
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pydicom
import torch
from sklearn.metrics import average_precision_score
from torch import nn

SEED = 20261116


def rebuild_images(data, ids, cache, original):
    """Recreate the 224 px oriented mid-sagittal images exactly as localize.py did."""
    import cv2
    from baseline import middle_slice
    from localize import geometry, image

    series = pd.read_csv(data / "train_series_descriptions.csv", dtype=str)
    series = series[series.series_description.eq("Sagittal T2/STIR")].set_index("study_id").series_id
    images = np.zeros((len(ids), 224, 224), np.uint8)
    for i, study in enumerate(ids):
        ds = pydicom.dcmread(middle_slice(data / "train_images" / study / series.loc[study]))
        _, directions, _, _ = geometry(ds)
        im = image(ds)
        if directions[0, 1] < 0:
            im = np.fliplr(im)
        if directions[1, 2] > 0:
            im = np.flipud(im)
        images[i] = cv2.resize(np.ascontiguousarray(im), (224, 224), interpolation=cv2.INTER_AREA)
        if (i + 1) % 250 == 0:
            print("images", i + 1, flush=True)
    np.save(cache, images)
    return images


def crops_at(images, centres, fields):
    from localize import crop

    out = np.zeros(centres.shape[:2] + (64, 64), np.uint8)
    for i in range(len(images)):
        for j in range(5):
            if np.isfinite(centres[i, j]).all():
                out[i, j] = crop(images[i], centres[i, j], fields[i])
    return out


def predict(net, crops, ids, keep):
    level = torch.arange(5).repeat(len(ids))
    x = torch.from_numpy(np.stack([crops, np.zeros_like(crops)], axis=2).reshape(-1, 2, 64, 64))
    rows = np.flatnonzero(keep)
    scores = []
    with torch.inference_mode():
        for k in range(0, len(rows), 256):
            r = torch.from_numpy(rows[k : k + 256])
            scores.append(net(x[r].float() / 255, level[r]).softmax(-1).numpy())
    return rows, np.concatenate(scores)


def train(crops, ids, grades, keep, manifest, out, tag):
    from paired_classifier import DiscClassifier

    study = np.repeat(ids, 5)
    level = torch.arange(5).repeat(len(ids))
    x = torch.from_numpy(np.stack([crops, np.zeros_like(crops)], axis=2).reshape(-1, 2, 64, 64))
    y = torch.from_numpy(grades)
    split = {p: np.flatnonzero(np.isin(study, manifest[p]) & keep) for p in ("train", "validation")}
    torch.manual_seed(SEED)
    torch.set_num_threads(3)
    net = DiscClassifier()
    opt = torch.optim.AdamW(net.parameters(), lr=0.0006)
    gen = torch.Generator().manual_seed(SEED)
    best = float("inf")
    for epoch in range(1, 11):
        net.train()
        order = split["train"][torch.randperm(len(split["train"]), generator=gen).numpy()]
        for k in range(0, len(order), 64):
            r = torch.from_numpy(order[k : k + 64])
            loss = nn.functional.cross_entropy(net(x[r].float() / 255, level[r]), y[r])
            opt.zero_grad()
            loss.backward()
            opt.step()
        net.eval()
        with torch.inference_mode():
            r = torch.from_numpy(split["validation"])
            value = nn.functional.cross_entropy(net(x[r].float() / 255, level[r]), y[r]).item()
        print("retrain", tag, "epoch", epoch, round(value, 5), flush=True)
        if value < best:
            best = value
            torch.save(net.state_dict(), out / f"model-{tag}-{SEED}.pt")
    net.load_state_dict(torch.load(out / f"model-{tag}-{SEED}.pt", weights_only=True))
    return net.eval()


def evaluate(name, net, val_crops, test_crops, ids, grades, keep, manifest, displacement):
    study = np.repeat(ids, 5)
    out = {}
    for phase, crops in (("validation", val_crops), ("test", test_crops)):
        rows, p = predict(net, crops, ids, keep & np.isin(study, manifest[phase]))
        out[phase] = pd.DataFrame(
            dict(
                study_id=study[rows],
                level=rows % 5,
                grade=grades[rows],
                displacement_mm=displacement[rows],
                p_normal_mild=p[:, 0],
                p_moderate=p[:, 1],
                p_severe=p[:, 2],
            )
        )
    val, test = out["validation"], out["test"]
    neg = np.sort(val.loc[val.grade.ne(2), "p_severe"].to_numpy())[::-1]
    cut = np.nextafter(neg[int(0.05 * len(neg))], np.inf)
    test["alert"] = test.p_severe.ge(cut)
    test["call"] = test[["p_normal_mild", "p_moderate", "p_severe"]].to_numpy().argmax(1)
    test["arm"] = name
    sev = test.grade.eq(2)
    far = test.displacement_mm.gt(20)
    confusion = pd.crosstab(test.grade, test.call).reindex(index=range(3), columns=range(3), fill_value=0)
    row = dict(
        arm=name,
        levels=len(test),
        severe=int(sev.sum()),
        tp=int((sev & test.alert).sum()),
        fp=int((~sev & test.alert).sum()),
        threshold=float(cut),
        severe_ap=float(average_precision_score(sev, test.p_severe)),
        accuracy=float((test.call == test.grade).mean()),
        moderate_recall=float(confusion.loc[1, 1] / confusion.loc[1].sum()),
        far_levels=int(far.sum()),
        far_severe=int((far & sev).sum()),
        far_tp=int((far & sev & test.alert).sum()),
        confusion=confusion.to_numpy().tolist(),
    )
    return row, test


def bootstrap(tests, draws=5000):
    """Paired study-level bootstrap of TP and severe-AP differences between arms."""
    arms = {t.arm.iloc[0][0]: t.sort_values(["study_id", "level"]).reset_index(drop=True) for t in tests}
    studies = arms["A"].study_id.unique()
    index = {s: np.flatnonzero(arms["A"].study_id.to_numpy() == s) for s in studies}
    rng = np.random.default_rng(SEED)
    out = {}
    for after, before in (("B", "A"), ("C", "E"), ("C", "A"), ("D", "E")):
        x, y = arms[after], arms[before]
        assert (x.study_id.to_numpy() == y.study_id.to_numpy()).all()
        sev = x.grade.eq(2).to_numpy()
        tp, ap = [], []
        for _ in range(draws):
            rows = np.concatenate([index[s] for s in rng.choice(studies, len(studies))])
            tp.append(((x.alert.to_numpy() & sev)[rows].sum() - (y.alert.to_numpy() & sev)[rows].sum()))
            ap.append(average_precision_score(sev[rows], x.p_severe.to_numpy()[rows])
                      - average_precision_score(sev[rows], y.p_severe.to_numpy()[rows]))
        out[f"{after}-{before}"] = dict(
            tp_difference_ci=np.percentile(tp, [2.5, 97.5]).tolist(),
            ap_difference_ci=np.percentile(ap, [2.5, 97.5]).round(4).tolist(),
        )
    return out


def main():
    global SEED
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("original", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--seed", type=int, default=SEED, help="training seed; outputs get a suffix")
    ap.add_argument("--images", type=Path, help="reuse an images224.npy cache")
    a = ap.parse_args()
    SEED = a.seed
    sys.path.insert(0, str(a.original))
    from baseline import GRADES, LEVELS
    from paired_classifier import DiscClassifier

    a.out.mkdir(parents=True, exist_ok=True)
    features = a.data / "paired-features-v1" / "sagittal.npz"
    sag = np.load(features)
    ids, fields = sag["ids"], sag["fields"]
    manifest = json.loads((a.original / "run-20261116" / "manifest.json").read_text())

    cache = a.images or a.out / "images224.npy"
    images = np.load(cache) if cache.exists() else rebuild_images(a.data, ids, cache, a.original)

    auto = crops_at(images, sag["predicted"], fields)
    diff = np.abs(auto.astype(int) - sag["crops"].astype(int))
    print("reproduction of cached automatic crops: max abs diff", diff.max(), "mean", diff.mean(), flush=True)
    assert diff.mean() < 0.5, "Rebuilt images do not reproduce the cached crops"
    auto = sag["crops"]
    reference = crops_at(images, sag["targets"], fields)
    np.savez_compressed(a.out / "reference-crops.npz", ids=ids, crops=reference)

    table = pd.read_csv(a.data / "train.csv", dtype={"study_id": str}).set_index("study_id")
    cols = ["spinal_canal_stenosis_" + level for level in LEVELS]
    grades = table.loc[ids, cols].apply(lambda v: v.map(GRADES)).fillna(-100).to_numpy("int64").ravel()
    targets = sag["targets"]
    # RSNA contains placeholder landmarks at pixel (5, 5); they project to the image corner.
    in_frame = np.isfinite(targets).all(axis=2) & (targets > 0.03).all(axis=2) & (targets < 0.97).all(axis=2)
    print("reference landmarks rejected as placeholders/out of frame",
          int((np.isfinite(targets).all(axis=2) & ~in_frame).sum()), flush=True)
    has_ref = in_frame.ravel()
    keep = (grades >= 0) & has_ref
    displacement = np.linalg.norm((sag["predicted"] - sag["targets"]) * fields[:, None, :], axis=2).ravel()
    test_mask = np.isin(np.repeat(ids, 5), manifest["test"])
    print(
        "test levels labelled", int(((grades >= 0) & test_mask).sum()),
        "with reference landmark", int((keep & test_mask).sum()), flush=True,
    )

    original = DiscClassifier()
    original.load_state_dict(
        torch.load(a.original / "paired-20261116" / "sagittal" / "model.pt", weights_only=True)
    )
    original.eval()
    retrained = train(reference, ids, grades, keep, manifest, a.out, "reference")
    # Same loop on automatic crops isolates the input change from the training-loop change.
    control = train(auto, ids, grades, keep, manifest, a.out, "automatic")

    rows, tests = [], []
    for name, net, crops in (
        ("A original weights / automatic crops", original, auto),
        ("B original weights / reference crops", original, reference),
        ("C reference-trained / reference crops", retrained, reference),
        ("D reference-trained / automatic crops", retrained, auto),
        ("E automatic-trained (same loop) / automatic crops", control, auto),
    ):
        r, t = evaluate(name, net, crops, crops, ids, grades, keep, manifest, displacement)
        rows.append(r)
        tests.append(t)
        print(json.dumps({k: v for k, v in r.items() if k != "confusion"}), flush=True)
    pd.concat(tests).to_csv(a.out / f"relocalized-test-{SEED}.csv", index=False)
    rows.append(dict(arm="paired study bootstrap, 5000 draws", differences=bootstrap(tests)))
    print(json.dumps(rows[-1]), flush=True)
    (a.out / f"relocalized-metrics-{SEED}.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
