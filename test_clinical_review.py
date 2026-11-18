"""Synthetic completeness-validator regressions; no clinical observations."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from clinical_review import prepare, validate


class RecordingChecks(unittest.TestCase):
    def test_recording_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            artifact = base / "fixture.html"
            artifact.write_text("Synthetic validator fixture", encoding="utf-8")
            record_path = base / "review.json"
            prepare(artifact, record_path)
            record = json.loads(record_path.read_text(encoding="utf-8"))
            self.assertFalse(validate(record, artifact, base)["recording_complete"])
            record["record_type"] = "synthetic_check"
            for case in record["cases"]:
                case.update(reader_id="synthetic-reader", review_date="2026-11-18",
                            first_assistance_status="before assistance",
                            technique_and_limitations="Synthetic excerpt",
                            disposition="unchanged", reason="Synthetic unchanged wording",
                            empty_group_interpretation="Synthetic observation")
                case["before"] = dict(grade="Moderate", findings="Synthetic findings",
                                      impression="Synthetic impression")
                case["after"] = dict(case["before"])
                case["levels"][case["target_level"]] = "Moderate"
                case["evidence"] = [dict(study_id=case["study_id"], level=case["target_level"],
                                         series_id="synthetic", instance=1, observation="Synthetic")]
                case["worksheet_path"] = case["study_id"] + ".txt"
                lines = ["Study " + case["study_id"]]
                for level, grade in case["levels"].items():
                    text = "Unread" if grade == "Unread" else "First: Moderate (before assistance) | Final: Moderate"
                    lines.append(level + " | " + text)
                (base / case["worksheet_path"]).write_text("\n".join(lines), encoding="utf-8")
            result = validate(record, artifact, base)
            self.assertTrue(result["recording_complete"], result["errors"])
            self.assertEqual(result["counts"]["pending_adjudication"], 2)
            for field, value in [("first_assistance_status", "after assistance was shown"),
                                 ("disposition", "changed"), ("worksheet_path", "missing.txt")]:
                bad = copy.deepcopy(record)
                bad["cases"][0][field] = value
                self.assertFalse(validate(bad, artifact, base)["recording_complete"], field)
            bad = copy.deepcopy(record)
            bad["cases"][0]["adjudication"] = dict(reviewer_id="synthetic-other",
                                                    verdict="supported", reason="Synthetic")
            self.assertFalse(validate(bad, artifact, base)["recording_complete"])
            bad["cases"][0].update(full_dicom_reviewed=True, level_numbering_verified=True)
            self.assertTrue(validate(bad, artifact, base)["recording_complete"])
            bad["cases"][0]["after"]["findings"] = "Synthetic changed findings"
            bad["cases"][0]["disposition"] = "changed"
            result = validate(bad, artifact, base)
            self.assertTrue(result["recording_complete"], result["errors"])
            self.assertEqual(result["counts"]["supported_changes"], 1)
            deferred = copy.deepcopy(record)
            case = deferred["cases"][0]
            case["disposition"] = "deferred"
            case["after"]["grade"] = "Insufficient images"
            case["levels"][case["target_level"]] = "Insufficient images"
            sheet = base / case["worksheet_path"]
            original = sheet.read_text(encoding="utf-8")
            sheet.write_text(original.replace("Final: Moderate", "Final: Insufficient images"), encoding="utf-8")
            result = validate(deferred, artifact, base)
            self.assertTrue(result["recording_complete"], result["errors"])
            self.assertEqual(result["counts"]["deferred"], 1)
            sheet.write_text(original.replace("L1/L2 | Unread", "L1/L2 | Final: Normal/mild"), encoding="utf-8")
            self.assertFalse(validate(record, artifact, base)["recording_complete"])
            sheet.write_text(original, encoding="utf-8")
            artifact.write_text("Changed build", encoding="utf-8")
            self.assertFalse(validate(record, artifact, base)["recording_complete"])


if __name__ == "__main__":
    unittest.main()
