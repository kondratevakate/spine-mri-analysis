"""Prepare and validate a clinician-authored reporting review (Python 3.11, stdlib).

This checks recording completeness. Image interpretation and adjudication are human tasks.
"""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LEVELS = ["L1/L2", "L2/L3", "L3/L4", "L4/L5", "L5/S1"]
CASES = {"1269700501": "L4/L5", "953639220": "L3/L4"}
GRADES = ["Normal/mild", "Moderate", "Severe", "Insufficient images"]


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(artifact, output):
    cases = []
    for study, level in CASES.items():
        cases.append({
            "study_id": study,
            "target_level": level,
            "reader_id": "",
            "review_date": "",
            "prior_exposure": "unknown",
            "first_assistance_status": "",
            "clinical_context": "Unavailable in this RSNA excerpt demo",
            "technique_and_limitations": "",
            "prior_examination_comparison": "Unavailable in this demo",
            "full_dicom_reviewed": False,
            "level_numbering_verified": False,
            "levels": {name: "Unread" for name in LEVELS},
            "before": {"grade": "", "findings": "", "impression": ""},
            "after": {"grade": "", "findings": "", "impression": ""},
            "disposition": "",
            "reason": "",
            "evidence": [],
            "reference_study_ids_viewed": [],
            "empty_group_interpretation": "",
            "needs_full_exam": True,
            "worksheet_path": "",
            "adjudication": {"reviewer_id": "", "verdict": "pending", "reason": ""},
        })
    result = {"schema_version": 1, "record_type": "unfilled_template",
              "artifact": {"path": str(artifact), "sha256": fingerprint(artifact)},
              "cases": cases}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(f"Created unfilled review template: {output}")


def validate(record, artifact, base):
    errors = []
    counts = {"cases": 0, "changed": 0, "unchanged": 0, "deferred": 0,
              "supported_changes": 0, "unsupported_changes": 0,
              "pending_adjudication": 0, "indeterminate_adjudication": 0}

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(record.get("schema_version") == 1, "Unsupported schema version")
    require(record.get("record_type") in ["clinician_observation", "synthetic_check"],
            "Set record_type explicitly after recording observations")
    require(record.get("artifact", {}).get("sha256") == fingerprint(artifact),
            "Artifact hash differs from the reviewed build")
    cases = record.get("cases", [])
    require(len(cases) == 2 and {c.get("study_id") for c in cases} == set(CASES),
            "This two-case walkthrough requires both specified fixtures exactly once")
    for case in cases:
        study = case.get("study_id")
        label = str(study)
        counts["cases"] += 1
        require(case.get("target_level") == CASES.get(study), label + ": wrong target level")
        for field in ["reader_id", "review_date", "clinical_context", "technique_and_limitations",
                      "prior_examination_comparison", "reason", "empty_group_interpretation"]:
            require(bool(str(case.get(field, "")).strip()), label + ": missing " + field)
        require(case.get("prior_exposure") in ["none_reported", "reported", "unknown"],
                label + ": specify prior exposure")
        assistance = case.get("first_assistance_status")
        require(assistance in ["before assistance", "after assistance was shown",
                               "historical entry, exposure untracked"],
                label + ": copy first-assistance status from the worksheet")
        for field in ["full_dicom_reviewed", "level_numbering_verified", "needs_full_exam"]:
            require(type(case.get(field)) is bool, label + ": expected boolean " + field)
        levels = case.get("levels", {})
        require(set(levels) == set(LEVELS), label + ": record all five level states")
        require(all(v in GRADES + ["Unread"] for v in levels.values()),
                label + ": invalid level state")
        for stage in ["before", "after"]:
            assessment = case.get(stage, {})
            require(assessment.get("grade") in GRADES, label + ": missing " + stage + " grade")
            for field in ["findings", "impression"]:
                require(bool(assessment.get(field, "").strip()),
                        label + ": missing exact " + stage + " " + field)
        before, after = case.get("before", {}), case.get("after", {})
        changed = any(before.get(k) != after.get(k) for k in ["findings", "impression"])
        disposition = case.get("disposition")
        require(disposition in ["changed", "unchanged", "deferred"], label + ": invalid disposition")
        if disposition in counts:
            counts[disposition] += 1
        if disposition == "changed":
            require(changed, label + ": changed requires an actual report-text change")
        if disposition == "unchanged":
            require(not changed, label + ": unchanged has different report text")
        if disposition == "deferred":
            require(after.get("grade") == "Insufficient images" and case.get("needs_full_exam"),
                    label + ": deferral must preserve uncertainty and request adequate imaging")
        require(levels.get(case.get("target_level")) == after.get("grade"),
                label + ": target-level state disagrees with final grade")
        evidence = case.get("evidence", [])
        require(bool(evidence), label + ": record inspected query images, including for deferral")
        for image in evidence:
            require(image.get("study_id") == study, label + ": evidence must identify the query study")
            require(image.get("level") == case.get("target_level"), label + ": image level mismatch")
            for field in ["series_id", "instance", "observation"]:
                require(bool(str(image.get(field, "")).strip()), label + ": missing image " + field)
        worksheet = case.get("worksheet_path", "")
        worksheet_path = base / worksheet
        require(bool(worksheet) and worksheet_path.is_file(), label + ": exported worksheet missing")
        if worksheet and worksheet_path.is_file():
            content = worksheet_path.read_text(encoding="utf-8-sig")
            require("Study " + str(study) in content, label + ": worksheet study mismatch")
            lines = content.splitlines()
            for level, grade in levels.items():
                if grade == "Unread":
                    expected = level + " | Unread"
                    require(expected in lines, label + ": unread state changed in worksheet " + level)
                else:
                    line = next((item for item in lines if item.startswith(level + " |")), "")
                    require(line.endswith("| Final: " + grade),
                            label + ": level grade differs from worksheet " + level)
            target = next((line for line in lines if line.startswith(case.get("target_level", "?") + " |")), "")
            require("First: " + before.get("grade", "?") + " (" in target,
                    label + ": first grade differs from worksheet")
            require("(" + str(assistance) + ") | Final:" in target,
                    label + ": assistance history differs from worksheet")
            require(target.endswith("| Final: " + after.get("grade", "?")),
                    label + ": final grade differs from worksheet")
        adjudication = case.get("adjudication", {})
        verdict = adjudication.get("verdict")
        require(verdict in ["pending", "supported", "unsupported", "indeterminate"],
                label + ": invalid adjudication")
        if verdict == "pending":
            counts["pending_adjudication"] += 1
        elif verdict in ["supported", "unsupported", "indeterminate"]:
            require(bool(adjudication.get("reviewer_id")) and
                    adjudication.get("reviewer_id") != case.get("reader_id"),
                    label + ": independent adjudicator required for a completed adjudication")
            require(bool(adjudication.get("reason")), label + ": adjudication rationale missing")
            if verdict == "indeterminate":
                counts["indeterminate_adjudication"] += 1
            else:
                require(case.get("full_dicom_reviewed") and case.get("level_numbering_verified"),
                        label + ": supported/unsupported verdict requires full study and numbering review")
                if disposition == "changed":
                    counts[verdict + "_changes"] += 1
    return {"record_type": record.get("record_type"), "artifact_sha256": fingerprint(artifact),
            "recording_complete": not errors, "counts": counts, "errors": errors,
            "interpretation": "Completeness check only. Human adjudication is recorded, not verified by this script. "
                              "Two selected cases cannot establish clinical benefit or diagnostic accuracy."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "validate"])
    parser.add_argument("record", type=Path)
    parser.add_argument("--artifact", type=Path, default=ROOT / "spine-reader-v2.html")
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    if args.command == "prepare":
        prepare(artifact, args.record.resolve())
        return 0
    record = json.loads(args.record.read_text(encoding="utf-8"))
    result = validate(record, artifact, args.record.resolve().parent)
    print(json.dumps(result, indent=2))
    return 0 if result["recording_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
