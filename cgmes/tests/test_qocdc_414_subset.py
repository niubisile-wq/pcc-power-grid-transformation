from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


EXPERIMENTS = Path(__file__).resolve().parents[2] / "experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

from run_qocdc_414_applicable_subset import (  # noqa: E402
    SOURCE,
    build_mutant,
    validate_package,
)


class QoCDC414SubsetTests(unittest.TestCase):
    def test_official_development_control_passes_implemented_subset(self) -> None:
        result = validate_package(SOURCE)
        self.assertTrue(result["passed"], result["failed_rule_ids"])
        self.assertEqual(result["implemented_levels"], [1, 2, 3, 4])
        self.assertEqual(result["not_implemented_levels"], [5, 6, 7, 8])

    def test_missing_profile_control_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "missing_profile.zip"
            build_mutant(SOURCE, target, "missing_model_profile")
            result = validate_package(target)
        self.assertIn("L2_required_header_fields", result["failed_rule_ids"])

    def test_unresolved_dependency_control_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "unresolved_dependency.zip"
            build_mutant(SOURCE, target, "unresolved_model_dependency")
            result = validate_package(target)
        self.assertIn("L4_Model_DependentOn_resolution", result["failed_rule_ids"])


if __name__ == "__main__":
    unittest.main()
