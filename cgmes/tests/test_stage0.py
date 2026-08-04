from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StageZeroTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            (ROOT / "corpus" / "official_cgmes_corpus_manifest.json").read_text(encoding="utf-8")
        )

    def test_all_download_hashes_match(self) -> None:
        for package in self.manifest["packages"]:
            path = ROOT / "corpus" / "downloads" / package["download_filename"]
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, package["download_sha256"])

    def test_manifest_has_frozen_assignments(self) -> None:
        splits = {package["split"] for package in self.manifest["packages"]}
        self.assertIn("development", splits)
        self.assertIn("internal_validation", splits)
        self.assertFalse(self.manifest["holdout_integrity"]["untouched_final_holdout_available"])

    def test_no_unverified_redistribution(self) -> None:
        for package in self.manifest["packages"]:
            if package["redistribution_allowed"]:
                self.assertTrue(
                    "Apache-2.0" in package["licence_status"]
                    or "CC BY-SA 4.0" in package["licence_status"]
                )
                if "CC BY-SA 4.0" in package["licence_status"]:
                    self.assertEqual(
                        package["licence_evidence_url"],
                        "https://www.entsoe.eu/data/cim/cim-conformity-and-interoperability/",
                    )
                    self.assertIn("ENTSO-E attribution", package["redistribution_policy"])
            else:
                self.assertEqual(
                    package["redistribution_policy"],
                    "Do not redistribute until an explicit applicable licence is verified.",
                )

    def test_post_freeze_reference_is_not_mislabeled_as_model_holdout(self) -> None:
        package = next(
            item
            for item in self.manifest["packages"]
            if item["corpus_id"] == "entsoe_application_profiles_library_main_110d92b"
        )
        self.assertEqual(package["split"], "reference_only_not_model_holdout")
        self.assertFalse(
            self.manifest["holdout_integrity"]["untouched_final_holdout_available"]
        )

    def test_protocol_artifacts_exist(self) -> None:
        required = [
            ROOT / "protocols" / "SOLO_CONFIRMATORY_PROTOCOL_v1.md",
            ROOT / "protocols" / "roundtrip_protocol_v1.yaml",
            ROOT / "protocols" / "baseline_contract_v1.yaml",
            ROOT / "corpus" / "licenses" / "README.md",
        ]
        self.assertTrue(all(path.is_file() and path.stat().st_size > 0 for path in required))


if __name__ == "__main__":
    unittest.main()
