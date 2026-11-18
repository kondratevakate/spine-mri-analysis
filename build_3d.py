"""Export actual TotalSegmentator masks and matching DICOM plane geometry for offline review."""

import base64
import io
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np
from PIL import Image
from skimage.measure import marching_cubes
from scipy.ndimage import zoom


def binary(a, dtype):
    return base64.b64encode(np.asarray(a, dtype=dtype).tobytes()).decode()


def jpeg(a):
    lo, hi = np.percentile(a, [1, 99])
    im = Image.fromarray(np.uint8(np.clip((a - lo) / max(hi - lo, 1), 0, 1) * 255))
    im.thumbnail((650, 650))
    f = io.BytesIO()
    im.save(f, format="JPEG", quality=90)
    return base64.b64encode(f.getvalue()).decode()


def surface(path):
    img = nib.load(path)
    data = np.asarray(img.dataobj, dtype=np.uint8)
    # Resample the binary mask on a 1.5 mm grid for surface extraction.
    scale = nib.affines.voxel_sizes(img.affine) / 1.5
    out = zoom(data, scale, order=0)
    if not out.any():
        return None
    verts, faces, _, _ = marching_cubes(np.pad(out, 1), 0.5, step_size=1)
    verts = (verts - 1) / scale
    verts = nib.affines.apply_affine(img.affine, verts)
    import vtk
    from vtk.util.numpy_support import (
        numpy_to_vtk,
        vtk_to_numpy,
        numpy_to_vtkIdTypeArray,
    )

    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(verts, deep=True))
    cells = vtk.vtkCellArray()
    cells.SetCells(
        len(faces),
        numpy_to_vtkIdTypeArray(
            np.c_[np.full(len(faces), 3), faces].astype(np.int64).ravel(), deep=True
        ),
    )
    poly = vtk.vtkPolyData()
    poly.SetPoints(points)
    poly.SetPolys(cells)
    dec = vtk.vtkQuadricDecimation()
    dec.SetInputData(poly)
    dec.SetTargetReduction(max(0, 1 - 18000 / len(faces)))
    dec.Update()
    smooth = vtk.vtkWindowedSincPolyDataFilter()
    smooth.SetInputConnection(dec.GetOutputPort())
    smooth.SetNumberOfIterations(18)
    smooth.SetPassBand(0.12)
    smooth.BoundarySmoothingOff()
    smooth.FeatureEdgeSmoothingOff()
    smooth.NormalizeCoordinatesOn()
    smooth.Update()
    mesh = smooth.GetOutput()
    v = vtk_to_numpy(mesh.GetPoints().GetData())
    f = vtk_to_numpy(mesh.GetPolys().GetData()).reshape(-1, 4)[:, 1:]
    triangles = (v - v.mean(axis=0))[f]
    signed_volume = (
        np.einsum(
            "ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])
        ).sum()
        / 6
    )
    # Marching-cubes winding can point inward. Export outward faces for WebGL culling.
    if signed_volume < 0:
        f = f[:, [0, 2, 1]]
    assert abs(signed_volume) > 0
    return dict(
        vertices=binary(v, "<f4"),
        faces=binary(f, "<u4"),
        bounds=[v.min(0).tolist(), v.max(0).tolist()],
        triangles=len(f),
        volume_mm3=float(abs(signed_volume)),
    )


def build(work, output):
    metadata = json.loads((work / "geometry.json").read_text())
    img = nib.load(work / "sagittal.nii.gz")
    vox = np.asarray(img.dataobj)
    index_points = nib.affines.apply_affine(
        np.linalg.inv(img.affine), [p["ras"] for p in metadata["landmarks"]]
    )
    k = int(round(np.median(index_points[:, 2])))
    metadata["display_instance"] = metadata["landmarks"][0]["source_instance"]
    for point, ijk in zip(metadata["landmarks"], index_points):
        point["uv"] = [
            float((ijk[0] + 0.5) / vox.shape[0]),
            float((ijk[1] + 0.5) / vox.shape[1]),
        ]
    meshes = {}
    for name in ["vertebrae", "intervertebral_discs", "sacrum"]:
        path = work / "segmentations" / (name + ".nii.gz")
        if path.exists():
            part = surface(path)
            if part:
                meshes[name] = part
    assert "vertebrae" in meshes and "intervertebral_discs" in meshes
    corners = nib.affines.apply_affine(
        img.affine,
        [
            [-0.5, -0.5, k],
            [vox.shape[0] - 0.5, -0.5, k],
            [vox.shape[0] - 0.5, vox.shape[1] - 0.5, k],
            [-0.5, vox.shape[1] - 0.5, k],
        ],
    )
    # Same-plane segmentation outlines for visual review, never classification scores.
    masks = {
        n: np.asarray(nib.load(work / "segmentations" / (n + ".nii.gz")).dataobj)
        for n in meshes
    }
    from skimage.segmentation import find_boundaries

    raw = vox[:, :, k].T
    lo, hi = np.percentile(raw, [1, 99])
    rgb = np.repeat(
        np.uint8(np.clip((raw - lo) / (hi - lo), 0, 1) * 255)[:, :, None], 3, axis=2
    )
    for name, color in [
        ("vertebrae", [225, 196, 146]),
        ("intervertebral_discs", [83, 223, 192]),
        ("sacrum", [145, 166, 220]),
    ]:
        if name in masks:
            rgb[find_boundaries(masks[name][:, :, k].T > 0, mode="outer")] = color
    f = io.BytesIO()
    Image.fromarray(rgb).save(f, format="PNG")
    metadata.update(
        meshes=meshes,
        sag=jpeg(raw),
        contours=base64.b64encode(f.getvalue()).decode(),
        corners=corners.tolist(),
    )
    import pandas as pd
    import pydicom
    from build_overview import axial_level, plane, jpg

    cache = Path(
        "C:/Projects/cache/rsna-lumbar-2024"
        if os.name == "nt"
        else "/mnt/c/Projects/cache/rsna-lumbar-2024"
    )
    series = pd.read_csv(cache / "train_series_descriptions.csv", dtype=str)
    selected = series[
        (series.study_id == metadata["study"])
        & (series.series_description == "Axial T2")
    ]
    folders = {
        s: cache / "train_images" / metadata["study"] / s for s in selected.series_id
    }
    pts = pd.read_csv(
        cache / "train_label_coordinates.csv", dtype={"study_id": str, "series_id": str}
    )
    pts = pts[
        (pts.study_id == metadata["study"])
        & pts.condition.str.endswith("Subarticular Stenosis")
    ]
    metadata["ax"] = []
    index = {}
    for point in metadata["landmarks"]:
        info, _ = axial_level(pts[pts.level == point["level"]], folders, index)
        if info:
            info["images"] = [
                jpg(
                    plane(pydicom.dcmread(folders[info["series"]] / f"{instance}.dcm")),
                    512,
                )
                for instance in info["instances"]
            ]
        metadata["ax"].append(info)
    vendor = Path("work/vendor")
    imports = {
        "three": "data:text/javascript;base64,"
        + base64.b64encode((vendor / "three.module.js").read_bytes()).decode(),
        "controls": "data:text/javascript;base64,"
        + base64.b64encode((vendor / "OrbitControls.js").read_bytes()).decode(),
    }
    template = Path("three-view.html").read_text(encoding="utf8")
    result = template.replace("__IMPORTS__", json.dumps({"imports": imports})).replace(
        "__VOLUME__", json.dumps(metadata, separators=(",", ":"))
    )
    license_text = (vendor / "THREE-LICENSE.txt").read_text(encoding="utf8")
    result = result.replace(
        "</body>",
        '<script type="text/plain" id="three-license">'
        + license_text
        + "</script></body>",
    )
    output.write_text(result, encoding="utf8")
    print(
        output,
        output.stat().st_size,
        {n: m["triangles"] for n, m in meshes.items()},
        flush=True,
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("work", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    build(a.work, a.output)
