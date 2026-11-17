# Physician workflow and critical review

**Disposition, 17 November 2026.** Ready for a moderated prototype review with a radiologist. Diagnostic sign-off, clinical deployment, and benefit claims require additional evidence. The reader task is to record the imaging appearance of the central canal at a named disc level, or explain that the available excerpts are insufficient.

## Work backwards from the decision

| Physician's question | Evidence in V2 | Residual gap |
|---|---|---|
| Which disc level am I looking at? | Simultaneous sagittal landmarks and five level rows; selected axial series and instance identifiers. | Landmark coordinates are estimated. Transitional anatomy and numbering require review against the complete examination. |
| Is the distinction visible on source images? | Whole sagittal plane, selected full axial T2 plane and adjacent planes when available. | Static, contrast-normalized previews, limited stack and resolution. The actual worst plane may lie outside the excerpt. No diagnostic DICOM windowing or complete PACS study. |
| Which examples help distinguish adjacent grades? | Up to five same-level independent studies per grade with fixed model/reference agreement. Each opens paired sagittal and axial source views. | Agreement here is with dataset labels. Selecting only agreements enriches easy cases, biases the visible spectrum and cannot estimate accuracy. |
| Can I disagree or defer without changing anyone else's score? | Grade or insufficient images per level, local persistence, blind mode, export of first/final reader entries. Unread levels remain unread. | A workstation file and browser-local state are a study tool. There is no signed clinical report, identity management or PACS handoff. |
| What can I conclude about referral or treatment? | The worksheet describes imaging only. | Symptoms, neurological findings, prior treatment, progression and original signed report are unavailable. |

## Evidence from the related work

- **Remedy Logic.** K241108, issued 30 October 2024, covers RAI's segmentation, quantitative measurements and export for qualified users who review and correct outputs. The indications specify adult lumbar T2 DICOM and exclusions including pregnancy, contrast studies, postoperative complications, scoliosis, tumor, infection and fracture. Pages 4 and 6 describe indications and the PACS workflow. This clearance supplies a workflow comparator. No regulatory evidence for V2, grading, nearest-neighbor retrieval, or recommendations for treatment follows from it. [FDA K241108](https://www.accessdata.fda.gov/cdrh_docs/pdf24/K241108.pdf)
- **RSNA.** The competition addresses central canal, bilateral foraminal and bilateral subarticular findings at five lumbar levels. This reader implements the central canal task with three released grades. IV/V disc-degeneration grades would require a different reference. The study split here is internal to the available training release. The published challenge test set is separate. [RSNA challenge](https://www.rsna.org/artificial-intelligence/ai-image-challenge/lumbar-spine-degenerative-classification-ai-challenge) · [LumbarDISC dataset paper](https://pubs.rsna.org/doi/10.1148/ryai.250480)
- **Clinical decisions.** US ACR guidance distinguishes uncomplicated low back pain from scenarios with red flags and persistent symptoms. NICE NG59 recommendation 1.3.8 links consideration of decompression for sciatica to failed nonsurgical care and imaging consistent with symptoms. These sources address different points in care. An imaging grade alone cannot supply the missing information. The interface therefore has no automatic urgency, referral or surgical decision. [ACR expert panel](https://pubmed.ncbi.nlm.nih.gov/34794594/) · [NICE NG59](https://www.nice.org.uk/guidance/ng59/chapter/Recommendations)
- **Recovered project context.** The Remedy Logic research chat identified PACS review and physician correction as the relevant benchmark. The value-study chat distinguished image concordance from a change to an existing report or consultation. Earlier reporting work distinguished level, compartment and side, and proposed measuring misses as well as alerts. V2 is a central-canal review experiment. Time saved, reporting improvement, referral benefit and improved patient outcomes have not been demonstrated.

## Which grades are confused?

Recomputed from the frozen V1 scores across 308 test studies and 1,540 levels. Each model has equal weight. Severe requires a mean severe score of at least 0.50; otherwise the larger of the remaining two scores determines the call. No abstention threshold is applied.

| RSNA reference ↓ / ensemble → | Normal/mild | Moderate | Severe |
|---|---:|---:|---:|
| Normal/mild | 1,331 | 8 | 0 |
| Moderate | 96 | 22 | 2 |
| Severe | 50 | 20 | 11 |

The moderate/severe boundary accounts for 22 of 176 errors. The most common error is moderate called normal/mild (96), followed by severe called normal/mild (50). At L4/L5, 8 severe levels were called moderate, 2 moderate levels severe, 26 moderate levels normal/mild and 25 severe levels normal/mild. A boundary-centered comparison is a useful reading question, but its value should also be tested on those larger misses. In the separate bank only 3 of 39 moderate and 6 of 34 severe L4/L5 studies agree with the fixed rule before image-eligibility checks. Do not alter the rule to fill a column.

## How retrieval works and how it could fail

The older system ranked a single 48 mm sagittal patch using knee-encoder embeddings. V2 uses bilateral same-level RSNA subarticular landmarks for retrospective plane selection in an Axial T2 series. Both sides must select the same or adjacent plane, at most 6 mm apart. Adjacent slices must preserve orientation and have no gap exceeding 7 mm. For a single verified query plane, ranking uses a single centered axial plane from each study and the whole sagittal image. Without a verified axial plane the system leaves the columns empty. These are prototype engineering criteria. Deployment would require a separately validated locator independent of existing annotations.

Of 1,540 query levels, 1,274 have a three-plane excerpt, 31 have a single verified plane and 235 have none. This is a coverage count under the stated geometry rules. It does not measure anatomical localization accuracy. At L4/L5 a three-case moderate pool means retrieval can change the order but cannot change which three cases are shown. Increasing the number of independently reviewed moderate examples could matter more than refining their rank.

Query and bank studies are disjoint. Within an eligible reference grade, score each candidate using the mean cosine of full-plane HOG descriptors from three axial T2 planes (75%) and cosine for the whole mid-sagittal image (25%). No knee patch, grade distance or severity probability is part of the ranking. Level, grade and frozen agreement select candidates; they do not establish anatomical relevance. Acquisition field of view, orientation, habitus and scanner appearance can dominate gradients. Display of the entire axial plane lets the reader inspect why a retrieved neighbor might be unsuitable.

**Next retrieval experiment.** Blind the matching method and randomize the ordering of the V1 patch neighbor, V2 full-image neighbor and a random same-level, same-grade candidate drawn from the identical eligible bank. Ask two radiologists which reference best matches canal morphology, which one actually helps grade the query, and when neither is suitable. Record agreement, ties, insufficient examples and handling of disparate acquisitions. A later morphology-based ranker could use independently reviewed dural-sac area, CSF effacement and root crowding if reliable masks and reader labels become available. None of these measurements are currently generated by V2.

An anatomical comparison has a precedent. Schizas and colleagues based their qualitative scale on the relative appearance of rootlets and cerebrospinal fluid within the dural sac on axial T2. Their seven-grade scale differs from the three RSNA competition categories. A reviewer could annotate visible CSF, rootlet separation and the worst affected plane for a prospective comparison, without imposing a mapping between the scales. [Original morphology study](https://pubmed.ncbi.nlm.nih.gov/20671589/)

## Independent reverse walkthrough and human test

The separate Codex review simulated a physician on V1 using study 953639220 at L3/L4. It found that every initially shown neighbor had an erroneous model call, the correct-only view had no severe reference, changing the global threshold could not record physician uncertainty for one level, and cropped images obscured surrounding anatomy. Its P0 findings were simultaneous levels, per-level reader judgment and correct-only references with honest empty states. Its P1 finding was independent first reading. V2's browser check exercises these actions, persistence, grade endpoints and worksheet generation. A simulation cannot establish how practicing physicians use the system.

For a moderated session, open V2 in blind mode before any exposure. Ask the radiologist to identify all five levels, inspect L3/L4 in study 953639220, record a grade or insufficient images and state the anatomical reason. Reveal references, ask whether the lack of a severe exemplar changes the conclusion, then export the worksheet. Repeat for study 1269700501 at L4/L5. Start subsequent comparative readers on counterbalanced cases to reduce recall.

Record wrong-level selections, use of adjacent slices, first-to-final grade changes, time per case, interpretation of an empty column, and whether full PACS review was requested. Treat inability to identify the active level, unintended overwrite, accidental disclosure during a blind read, or an exported normal grade for an unread level as a blocking failure. Verify the clinical interpretation with full DICOM and an independent reference reader before any quality claim.

**Browser retest finding.** In the first V2 candidate, revealing assistance exposed other levels and a subsequent toggle could mislabel a first response as blind. The revised reader opens each level blind, reveals only the selected level, stores whether that study/level has already been exposed in this browser, and exports the first entry as before or after assistance. This record cannot detect prior exposure elsewhere or after browser state is cleared. The retest also identified an otherwise usable single-plane query. Single-plane comparison now uses the center plane of both studies with the same sagittal context.

| Final review fixture | Observed result in the browser |
|---|---|
| Study 1269700501, L4/L5 | Three query planes. Three moderate and five severe reference cards. The paired view changes both axial instance numbers together and preserves sagittal context. |
| Study 953639220, L3/L4 | One verified query plane. Five moderate cards and no severe card. The paired view stays on the matched center planes. |
| Record, reveal, hide, change levels, reload | First and final judgments remain distinct. A previously exposed level is marked as assisted at first entry. Other unread levels remain unread. All five rows fit the 1280 by 720 review viewport. |
