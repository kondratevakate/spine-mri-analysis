"""Reconstruct one native DICOM series and independently project RSNA landmarks."""

import argparse
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import pandas as pd
import pydicom
from PIL import Image, ImageDraw


def build(cache, study, output):
    output.mkdir(parents=True, exist_ok=True)
    series = pd.read_csv(cache / "train_series_descriptions.csv", dtype=str)
    selected = series[
        (series.study_id == study) & (series.series_description == "Sagittal T2/STIR")
    ]
    series_id = selected.series_id.item()
    folder = cache / "train_images" / study / series_id
    slices = [pydicom.dcmread(f) for f in folder.glob("*.dcm")]
    direction = np.array(slices[0].ImageOrientationPatient).reshape(2, 3)
    normal = np.cross(*direction)
    slices.sort(key=lambda ds: np.dot(ds.ImagePositionPatient, normal))
    positions = np.array([ds.ImagePositionPatient for ds in slices], float)
    step = np.median(np.diff(positions, axis=0), axis=0)
    assert (
        np.max(abs(positions - positions[0] - np.arange(len(slices))[:, None] * step))
        < 0.1
    )
    assert all(
        np.allclose(ds.ImageOrientationPatient, direction.ravel(), atol=1e-4)
        for ds in slices
    )
    assert all(np.allclose(ds.PixelSpacing, slices[0].PixelSpacing) for ds in slices)
    volume = np.stack([ds.pixel_array.T for ds in slices], axis=2).astype(np.float32)
    spacing = np.array(slices[0].PixelSpacing, float)
    affine = np.eye(4)
    affine[:3, 0] = direction[0] * spacing[1]
    affine[:3, 1] = direction[1] * spacing[0]
    affine[:3, 2] = step
    affine[:3, 3] = positions[0]
    lps_to_ras = np.diag([-1.0, -1.0, 1.0, 1.0])
    ras = lps_to_ras @ affine
    nib.save(nib.Nifti1Image(volume, ras), output / "sagittal.nii.gz")
    points = pd.read_csv(
        cache / "train_label_coordinates.csv", dtype={"study_id": str, "series_id": str}
    )
    points = points[
        (points.study_id == study)
        & (points.series_id == series_id)
        & (points.condition == "Spinal Canal Stenosis")
    ]
    ds = sorted(slices, key=lambda s: float(s.ImagePositionPatient[0]))[
        len(slices) // 2
    ]
    middle = next(
        i for i, s in enumerate(slices) if s.InstanceNumber == ds.InstanceNumber
    )
    landmarks = []
    features = np.load(cache / "paired-features-v1" / "sagittal.npz")
    index = list(features["ids"]).index(study)
    target = features["targets"][index]
    pred = features["predicted"][index]
    flip = np.array([direction[0, 1] < 0, direction[1, 2] > 0])
    for row in points.sort_values("level").itertuples():
        original = next(s for s in slices if s.InstanceNumber == row.instance_number)
        world = np.array(original.ImagePositionPatient) + direction.T @ (
            np.array([row.x, row.y]) * spacing[::-1]
        )
        projected = (
            direction @ (world - np.array(ds.ImagePositionPatient)) / spacing[::-1]
        )
        uv = (projected + 0.5) / [ds.Columns, ds.Rows]
        uv = np.where(flip, 1 - uv, uv)
        k = len(landmarks)
        assert np.allclose(uv, target[k], atol=1e-6)
        landmarks.append(
            dict(
                level=row.level,
                source_instance=int(row.instance_number),
                ras=(world * [-1, -1, 1]).tolist(),
                uv=uv.tolist(),
                model_uv=pred[k].tolist(),
                error_mm=float(
                    np.linalg.norm((uv - pred[k]) * features["fields"][index])
                ),
            )
        )
    pixels = ds.pixel_array.astype(float)
    lo, hi = np.percentile(pixels, [1, 99])
    pixels = np.uint8(np.clip((pixels - lo) / (hi - lo), 0, 1) * 255)
    if ds.PhotometricInterpretation == "MONOCHROME1":
        pixels = 255 - pixels
    if flip[0]:
        pixels = np.fliplr(pixels)
    if flip[1]:
        pixels = np.flipud(pixels)
    screen = Image.fromarray(pixels).convert("RGB").resize((700, 700))
    draw = ImageDraw.Draw(screen)
    for p in landmarks:
        for name, color in [("uv", "#70f0bd"), ("model_uv", "#ff705f")]:
            x, y = np.array(p[name]) * 700
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), outline=color, width=3)
            draw.text(
                (x + 9, y - 9),
                p["level"] + (" reference" if name == "uv" else " old model"),
                fill=color,
            )
    screen.save(output / "marker-audit.png")
    meta = dict(
        study=study,
        series=series_id,
        shape=list(volume.shape),
        affine=ras.tolist(),
        middle_index=middle,
        middle_instance=int(ds.InstanceNumber),
        landmarks=landmarks,
        voxel_mm=nib.affines.voxel_sizes(ras).tolist(),
        volume_orientation=nib.aff2axcodes(ras),
    )
    (output / "geometry.json").write_text(json.dumps(meta, indent=2), encoding="utf8")
    print(
        json.dumps(
            {
                k: meta[k]
                for k in ["shape", "voxel_mm", "volume_orientation", "middle_instance"]
            }
        ),
        flush=True,
    )
    print(
        "Landmark errors mm", [round(p["error_mm"], 1) for p in landmarks], flush=True
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cache", type=Path)
    p.add_argument("study")
    p.add_argument("output", type=Path)
    args = p.parse_args()
    build(args.cache, args.study, args.output)
