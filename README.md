# Lumbar MRI reader review

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
