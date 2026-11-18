# Handoff: from lumbar grades to physician-authored report changes

Prepared 18 November 2026. Independent review chat `01a1ea8a-3af6-70b3-b4fd-bbe11a85498d`; implementation chat `01a1e85b-ebb7-71a1-a80b-000c234394f5`.

## Objective and ownership

Evaluate whether viewing source-context examples helps a radiologist write an anatomically supported sentence in Findings or Impression, retain an existing sentence, or explicitly defer judgment. Record the precise wording and the query images supporting it. Grade agreement is a secondary observation.

The current worksheet records central-canal decisions at five lumbar levels and browser-local assistance exposure. A complete clinical report also needs clinical information, technique, comparison, other anatomical findings, limitations, and the physician's final interpretation.

This handoff adds a recording and verification workflow. The implementation chat owns changes to the viewer, generator and models. The current handoff does not authorize recruitment, clinical deployment or publication. A moderated reader session and independent clinical adjudication remain pending.

Repository `C:/Projects/02_academia/studies/spine-mri-analysis`, branch `main`. Reviewed source base `184bea0`. No remote was configured when this handoff was prepared. The HTML with embedded RSNA images is locally available and Git-ignored. Source code alone does not reproduce the image package. See [README](README.md) for build inputs and packaging.

## Read first

1. [STATE](STATE.md) and the opening correction in [REVIEW](REVIEW.md).
2. This handoff and the [V2 reader](spine-reader-v2.html).
3. [Browser check](review_reader.py), [clinical recording tool](clinical_review.py), and its [synthetic regressions](test_clinical_review.py).

## Evidence and correction to the earlier review

The independent walkthrough used browser automation to exercise actual controls and downloaded worksheets on 17 November. It initially found global assistance disclosure and false blind labels after hiding assistance. A fresh-profile retest verified the fix: blind default, reveal for the selected level, persistent exposure history, first/final answers and honest empty groups. These observations were simulated actions by Codex. No radiologist participated.

On 18 November the owning implementation recorded a source-coordinate audit finding a 31.0 mm displacement of the original L4/L5 marker in study 1269700501. Current V2 displays RSNA reference projections and omits missing locations. Original model scores still use their old crop locations. See [the marker audit and its limitations](REVIEW.md#marker-audit-and-3d-update-18-november-2026) and [audit code](audit_markers.py). This session read the audit record; it did not independently repeat the DICOM audit.

The browser regression was rerun successfully on the current local artifact while preparing this handoff. That result establishes interaction behavior only. Every clinical session must first verify numbering and source localization against the complete examination. The frozen model/reference agreement filter and old scores require re-evaluation after localization review. The examples are selected by agreement with dataset labels, and their clinical correctness remains a question for independent readers.

| Fixture | Current behavior checked | Clinical task |
|---|---|---|
| 1269700501, L4/L5 | Three query planes, three moderate and five severe examples; source comparison changes both axial planes | State the initial report wording, inspect examples, then preserve or revise the sentence and identify supporting query slices |
| 953639220, L3/L4 | One query plane, five moderate examples, zero severe examples; paired comparison disables adjacent-plane navigation | Explain what the absent severe group means, assess adequacy of the available images, and retain, revise or defer wording |

Browser results are saved locally under `work/clinical-handoff/browser/`. The fixture selection is deliberate and unsuitable for estimating population accuracy or average benefit. Prior exposure in another browser or an earlier session cannot be inferred from local storage.

Build fingerprint checked during handoff preparation: `51666f74933a6cefeb1b582f7505dfccf2aa52df1be7c9a5964b73cb1f938e27` (SHA-256 of local `spine-reader-v2.html`). The synthetic validator regressions passed, including incomplete records, exposure mismatch, missing worksheets, false change claims, supported-change prerequisites, deferral, unread-state corruption and changed artifacts. An unfilled pilot template was created at `work/clinical-handoff/reader-01.json` and correctly failed completeness validation. No human result has been entered.

## Reporting sources checked in this session

The intended jurisdiction is the United States. Professional guidance, regulatory device indications and dataset annotations have different scopes.

| Source | Verified version and relevant content | Use in the review |
|---|---|---|
| [ACR Communication of Diagnostic Imaging Findings](https://gravitas.acr.org/PPTS/DownloadPreviewDocument?DocId=74) | Revised 2025, Resolution 9, confirmed in the downloaded PDF chronology. Sections II.B-D cover report components, limitations, clinical questions, comparison, impression, proofreading and nonroutine communication | Review whether the reader's wording answers the supplied question and accurately documents limitations. Record critical-result communication when applicable to a future full clinical case |
| [ACR-ASNR-SABI-SSR MRI of the Adult Spine](https://www.acr.org/-/media/ACR/Files/Practice-Parameters/MR-Adult-Spine.pdf) | Revised 2023. The radiologist-quality section discusses alignment, discs, canal/foraminal narrowing, causes and nerve displacement/compression | Assess level, side, compartment, cause and affected neural structure where visible |
| [NASS-ASSR-ASNR Lumbar Disc Nomenclature 2.0](https://doi.org/10.1016/j.spinee.2014.04.022) | 2014 consensus terminology for disc morphology and localization | Use consistent words for disc findings; explain numbering in transitional anatomy |
| [RSNA RadReport](https://radreport.org/?language=en) | Examples of reporting practice. The site states that new template review/publication stopped in December 2022 and points to RadElement | A template can organize data; its existence does not establish a universal mandatory lumbar report format |
| [ACR imaging-AI announcement](https://www.acr.org/News-and-Publications/Media-Center/2026/first-practice-parameter-for-imaging-ai) | 5 May 2026 announcement of the ACR-SIIM practice parameter, describing local acceptance testing and ongoing monitoring | Supports the need to test the intended workflow locally. This session reviewed the announcement, not the full AI parameter |
| [FDA K241108](https://www.accessdata.fda.gov/cdrh_docs/pdf24/K241108.pdf) | Cleared 30 October 2024. PDF page 4 gives indications; pages 5-6 describe software and PACS workflow | Comparator for physician review/correction of segmentation and measurements. The clearance applies to RemedyLogic RAI and provides no clearance for this prototype or retrieval method |
| [RSNA challenge](https://www.kaggle.com/competitions/rsna-2024-lumbar-spine-degenerative-classification) and [LumbarDISC paper](https://pubs.rsna.org/doi/10.1148/ryai.250480) | Labels across five conditions and five lumbar levels; released competition grades are normal/mild, moderate and severe | V2 covers central canal only. Dataset labels and selected exemplar agreement cannot establish the clinical validity of a report change |

Source access was checked on 18 November 2026 in this chat. ACR's legacy PDF URLs sometimes redirect incorrectly. The current communication PDF was successfully read from the Gravitas download URL using Python requests and pypdf. Local legal requirements and institution-specific reporting policies were outside this review.

## Moderated radiologist session

Use a fresh browser profile for each reader and record their stated prior exposure. Obtain the full source examination for clinical adjudication. If only the demo excerpts are available, explicitly retain that limitation and allow deferral. Clinical history and prior examinations are unavailable in these fixtures; record this as missing information.

1. Before showing assistance, ask the radiologist to verify the named level and review the available source images. Record all five level states, leaving unreviewed levels as Unread.
2. Ask for the exact provisional Findings and Impression sentences for the target finding, a grade or Insufficient images, and the image evidence. Record the initial text before clicking Reveal. Export the worksheet to preserve this stage.
3. Reveal assistance for that level and inspect full-context examples. Ask which examples were useful and why. In 953639220, ask what an empty severe group permits the reader to conclude. It records exemplar availability; it provides no evidence that severe disease is absent in the query.
4. Ask: "Which exact sentence in Findings or Impression would you change after viewing these examples, and which query image supports that change?" Also allow unchanged wording and explicit deferral. Record final text, reason, source series/instance, examples viewed, and whether a complete examination is needed.
5. Export the final worksheet. Retain the first export separately. The recording tool checks the final worksheet against both grades and the stored exposure label. It also checks that Unread levels remain Unread.
6. Ask an independent radiologist to review the complete study and numbering, then judge the proposed wording. Record supported, unsupported or indeterminate with a reason. Initially hide the exemplar ranking and model answer from this adjudicator to reduce anchoring. Pending adjudication remains visible in summaries.

For image evidence use query study ID, named level, series ID, instance number and a short visible anatomical observation. For deferral, document the inspected images and the specific missing evidence. A reference patient's slice cannot substitute for the query patient's evidence.

The JSON record captures target-finding excerpts. The full-report fields still need clinical context, technique, comparison, additional anatomical findings, limitations and physician signature in a future clinical integration. Current browser exports contain no Findings or Impression text, so those sentences must be recorded separately during this pilot.

## Executable verification

Run from the repository root with Python 3.11. The existing browser script uses desktop Edge at its documented Windows path. The clinical tool and synthetic tests use the Python standard library.

```powershell
python -m pip install -r requirements-reader.txt
python review_reader.py spine-reader-v2.html work/clinical-handoff/browser
python -m unittest test_clinical_review.py
python clinical_review.py prepare work/clinical-handoff/reader-01.json
```

`prepare` refuses to overwrite an existing record. It creates two unfilled cases and fingerprints the actual HTML with SHA-256. Fill the record from the human session, set `record_type` to `clinician_observation`, and store exported worksheets beside it. Use relative worksheet paths. Set `first_assistance_status` to the exact parenthetical label in the worksheet. Record any known earlier exposure separately.

Example shape for one evidence entry, using placeholders that must be replaced by observed identifiers:

```json
{"study_id": "953639220", "level": "L3/L4", "series_id": "observed-series-id", "instance": "observed-instance", "observation": "Reader-authored description of the visible finding or missing evidence"}
```

Then run:

```powershell
python clinical_review.py validate work/clinical-handoff/reader-01.json
```

Exit 0 means recording fields and worksheet consistency passed. Exit 1 means incomplete or inconsistent recording, including a build hash mismatch. Missing or malformed input produces a nonzero Python error. The output reports every incomplete field and raw denominators for changed, unchanged, deferred, supported changes, unsupported changes and unresolved adjudications. It does not automatically interpret images or verify a human's assertions. Pending adjudication can coexist with a complete record. Synthetic tests use `synthetic_check` and temporary files; they provide no clinician observations.

The existing browser script checks source rendering and worksheet generation. The earlier independent walkthrough also exercised actual worksheet downloads. For this pilot the final exported file is independently read by `clinical_review.py`, closing the connection between browser output and recorded observations.

## Acceptance and next action

Proposed acceptance criteria for this moderated prototype review:

- The active study and level are correctly identified on the source examination. Record any mismatch and stop interpretation of that affected finding until clarified.
- Assistance exposure is confined to the selected level and its history survives hiding assistance. Unread, assessed and deferred states remain distinct.
- Both fixture paths work, including single-plane comparison and the empty severe group.
- Every target finding has exact before/after wording, a rationale, source-image identifiers, exposure history and a consistent worksheet. Retained wording and deferral are valid outcomes.
- Any claim that a change improves clinical reporting is supported by independent full-study review. Record unsupported changes and indeterminate judgments with the same completeness as supported changes.

After this two-case session, the first research decision is whether examples help a physician make a useful, supported wording change. Further benefit testing would require a prespecified case set and denominators, including normal/mild misses, image-inadequate cases and anatomical variation, with a full-examination unassisted comparator and controlled reader order. Size, precision and clinical endpoints remain to be agreed before that experiment. These two fixtures cannot answer referral benefit, treatment benefit, time savings or external-hospital performance.

## Continuation prompt

Continue in `C:/Projects/02_academia/studies/spine-mri-analysis`. Read STATE.md, the marker correction in REVIEW.md, and CLINICAL_HANDOFF.md. Run the browser regression and synthetic recording checks. Keep current viewer and model ownership with the implementation chat. Prepare the two-case moderated radiologist review, recording exact Findings/Impression sentences before and after assistance, query image evidence, exposure history and deferral. Verify source numbering against full DICOM before interpreting model suggestions. Use clinical_review.py to prepare and validate the recording. Report unresolved adjudication and unsupported changes explicitly. A clinician session has not yet been conducted.
