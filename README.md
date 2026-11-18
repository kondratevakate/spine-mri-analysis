# Lumbar MRI reader review

**18 November update.** Open **spine-3d.html** for the single-study TotalSegmentator prototype. Drag to rotate, use the wheel to zoom, choose a disc level and press **Focus level**. The adjacent large image supports zoom and pan. Its **Segmentation** checkbox overlays the original masks, and **Axial** opens an independently acquired axial T2 plane. All assets are embedded.

A source-coordinate audit found that the earlier automatic L4/L5 marker in study 1269700501 was displaced by 31.0 mm from the RSNA reference. The updated V2 reader uses dataset reference locations, with missing locations omitted. Its older model scores still reflect the original crops. The audit and 3D limitations are recorded in [REVIEW.md](REVIEW.md).

To reproduce the 3D example, install TotalSegmentator 2.18.0 in an environment supporting its native libraries, then run the following from the repository root. This workstation used Ubuntu/WSL because Windows application control blocked SimpleITK and VTK. Data paths in the surface builder support the existing Windows and WSL cache mounts.

```text
python prepare_volume.py RSNA_CACHE 1269700501 work/volume-1269700501
python run_segmentation.py
python fetch_3d_assets.py
python build_3d.py work/volume-1269700501 spine-3d.html
python review_3d.py spine-3d.html SCREENSHOT_DIRECTORY
```

The 3D surfaces come from total_mr, task 852, at 3 mm resolution. Native data contain 15 sagittal slices with 4.8 mm inter-slice spacing. The surfaces are smoothed for display; the original masks supply the 2D outlines. The example demonstrates one study. Detailed posterior elements, canal narrowing, accurate measurements and automatic vertebral numbering require separate evaluation. [TotalSegmentator implementation](https://github.com/wasserth/TotalSegmentator)

Open **spine-reader-v2.html** from the local review package in Edge, Firefox or Chrome. It embeds the images and works offline. The earlier **spine-review.html** is the adjustable ensemble laboratory. The two files are independent. The repository contains the templates, builders, review findings and browser checks. The separately packaged HTML files contain RSNA-derived images.

## Five-minute walkthrough

1. Open V2. All five estimated disc levels appear on the sagittal image and in the level list. Start at study 1269700501, L4/L5. Inspect the axial T2 plane and its two neighbors.
2. Choose **Show references for this level**. The default comparison is moderate versus severe. The separate library contains 299 validation studies. Only a matching named level with agreement between the fixed ensemble and RSNA label can appear. Click a case to compare both sagittal overviews and axial planes.
3. Choose a reader grade or **Insufficient images**. Change level and return. The entry belongs to that study and level. The comparison selector also supports the two immediate neighbors of a provisional grade. Endpoints have only one neighbor.
4. Each level opens in **Blind read**. Record your first judgment, reveal assistance, then retain or revise it. Export the reader worksheet. The exported text preserves the first entry, whether assistance had previously been shown on that level in this browser, and the final entry. Blind mode after earlier exposure cannot undo that exposure.
5. Try study 953639220, L3/L4. An empty severe column is a possible and intended result. Review how the physician handles that gap. Open V1 to investigate ensemble weights, thresholds and cohort errors separately.

## Build and test

The delivered HTML runs without Python. For a V2 rebuild, supply the original RSNA DICOM tree, its `train_label_coordinates.csv`, `train_series_descriptions.csv`, the fitted localizer cache `paired-features-v1/sagittal.npz`, and the frozen V1 HTML or its JSON payload. Python 3.11 dependencies for V2 are listed in `requirements-reader.txt`. Use paths to local inputs:

```text
python build_overview.py RSNA_CACHE spine-review.html spine-reader-v2.html
python review_reader.py spine-reader-v2.html SCREENSHOT_DIRECTORY
```

The browser check uses desktop Edge on Windows. Opening the HTML alone exercises the normal reviewer entry point on other platforms. V1's original training and transfer dependencies are recorded in [STATE.md](STATE.md). The builders do not retrain the four original lumbar classifiers. Local builds need permission to access the source images. [RSNA dataset](https://imaging.rsna.org/dataset/6/)

See [REVIEW.md](REVIEW.md) for evidence, confusion counts, usability findings and the proposed radiologist session. Human testing and evaluation on external hospitals remain open.

The ZIP also includes screenshots, a SHA-256 manifest and a portable Git repository. Extract the package before opening the HTML. To inspect its commit, use `git clone source.bundle lumbar-review-source` from the extracted directory. To repackage an already verified build, run `python package_review.py OUTPUT_DIRECTORY` from the committed source checkout.
