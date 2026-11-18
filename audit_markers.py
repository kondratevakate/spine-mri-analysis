"""Audit saved locator points and migrate the viewer to available RSNA reference points."""

import json
from pathlib import Path
import numpy as np


def audit(cache, payload, output):
    source = np.load(cache / "paired-features-v1/sagittal.npz")
    ids = {s: i for i, s in enumerate(source["ids"])}
    data = json.loads(payload.read_text(encoding="utf8"))
    rows = data["q"] + list(data["bank"].values())
    for row in rows:
        k = ids[row["id"]]
        row["xy"] = [
            p.tolist() if np.isfinite(p).all() else None for p in source["targets"][k]
        ]
    sel = [ids[r["id"]] for r in data["q"]]
    dist = np.linalg.norm(
        (source["predicted"][sel] - source["targets"][sel])
        * source["fields"][sel, None, :],
        axis=-1,
    )
    valid = np.isfinite(dist)
    result = dict(
        defined="In-plane Euclidean displacement from RSNA point projected to the displayed sagittal plane",
        test_studies=len(sel),
        valid_levels=int(valid.sum()),
        missing_levels=int((~valid).sum()),
        median_mm=float(np.nanmedian(dist)),
        p95_mm=float(np.nanpercentile(dist, 95)),
        over_10mm=int(np.sum(dist > 10)),
        over_20mm=int(np.sum(dist > 20)),
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "marker-audit.json").write_text(
        json.dumps(result, indent=2), encoding="utf8"
    )
    (output / "reader-reference-data.json").write_text(
        json.dumps(data, separators=(",", ":")), encoding="utf8"
    )
    print(result)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    for name in ["cache", "payload", "output"]:
        p.add_argument(name, type=Path)
    args = p.parse_args()
    audit(args.cache, args.payload, args.output)
