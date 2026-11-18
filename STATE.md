# Interactive lumbar MRI review

## Current review candidate

On 18 November the classifier was re-evaluated with RSNA-landmark crops (`relocalize.py`): localization explains part of the moderate errors and a non-significant 0.05-0.07 severe-AP gain, while most severe misses persist with oracle crops. The per-step error budget is `pipeline.html`. Details in REVIEW.md, first section.

The independent review handoff now connects the five-level worksheet to physician-authored Findings/Impression changes, query-image evidence and independent full-study adjudication. Read [CLINICAL_HANDOFF.md](CLINICAL_HANDOFF.md) for the session record, reporting sources, executable checks and next clinical step. The current browser regression passed during handoff preparation. Human reporting utility remains untested.

On 18 November, a landmark audit found a 31 mm L4/L5 displacement in the initial case. The reader now displays RSNA reference coordinates, and a single-study `spine-3d.html` shows actual TotalSegmentator masks with interactive level focus. See the new opening sections of README and REVIEW. Original classifier inputs and retrieval features need re-evaluation after localization review. The 3D viewer has passed local interaction checks and source-plane visual inspection.

The source repository contains the original ensemble workbench and a second, five-level physician reader. Open the packaged `spine-reader-v2.html` for the physician review. See [README.md](README.md) for entry points and [REVIEW.md](REVIEW.md) for the regulatory comparison, clinical limits, measured grade confusions, matching method and independent usability findings. The sections below describe the first workbench.

## Objective

Review the effect of changing an ensemble on a named lumbar level. The same screen must show the MRI, the assigned grade, the reference, cohort errors, and up to five visually similar cases from each of two selected reference grades. A reviewer can restrict examples to correct, incorrect, or deferred calls and open the two source-image regions side by side.

## Implementation

- The offline entry point is `spine-review.html`. Its images, model outputs, and similarity index are embedded. Use a desktop browser for simultaneous access to the three panels.
- The test selector contains 308 RSNA lumbar studies, each with five named levels. The comparison bank contains 299 other studies. Central canal labels are normal/mild, moderate, and severe. There are no IV/V labels in this task.
- Four lumbar classifiers and a knee-pretrained ConvNeXt-T supply three-class scores. The latter uses a frozen encoder and a multinomial logistic head fitted to 256 original training studies. Its standardized embeddings also rank same-level crops within each reference grade by cosine similarity. The head and feature scaler use training data only. The displayed similarities are quantized to 16 bits for storage.
- The 48 mm region is centered on the original sagittal model localizer. The viewer samples comparison patches from the oriented DICOM image. The marker color and caption follow the current decision. Threshold edits do not change the location or estimate a tissue boundary.
- The test cohort was inspected during earlier experiments. The initial L4/L5 case was deliberately selected near the severe decision threshold to demonstrate the interaction. The initial threshold of 50% and equal weights are demonstration settings. Tuning them is exploratory.

## Verified example

Study 1269700501, L4/L5, has a severe RSNA reference. The equal-weight severe score is 45.9%. Lowering the threshold from 50% to 35% changes the decision from moderate to severe. Across 1,540 test levels this changes severe detections from 11/81 to 40/81 and false severe alerts from 2/1,459 to 23/1,459. A visual match and agreement with the RSNA grade do not establish clinical equivalence or a treatment decision.

## Rebuild and verify

`build_panel.py CACHE ORIGINAL_LUMBAR_PROJECT TRANSFER_DIRECTORY OUTPUT_HTML` reads the cached RSNA DICOMs and localizer, original experiment splits and predictions, and the frozen knee checkpoint and extraction code in the transfer directory. It uses Python 3.11, timm, PyTorch, scikit-learn, pandas, OpenCV and the imports of the original research scripts. The viewer template is `panel.html`.

`python work/review_panel.py OUTPUT_DIRECTORY` exercises the rendered page in Edge, checks grade switches, live cohort counts, review deferral, zero and single-model settings, class and case changes, comparison dialogs and mobile width. It captures PNGs for visual inspection. The dataset and fitted models have not been externally validated for clinical use.
