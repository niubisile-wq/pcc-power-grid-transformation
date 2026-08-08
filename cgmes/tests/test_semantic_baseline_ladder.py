from __future__ import annotations

from pathlib import Path
import sys
import unittest


EXPERIMENTS = Path(__file__).resolve().parents[2] / "experiments"
if str(EXPERIMENTS) not in sys.path:
    sys.path.insert(0, str(EXPERIMENTS))

from run_pcc_v2_attack_matrix import transform  # noqa: E402
from run_pcc_v2_semantic_baseline_ladder import (  # noqa: E402
    attribute_invariants_accept,
    global_identity_accepts,
    task_footprint_accepts,
)


def fixture() -> dict:
    return {
        "assets": {
            "a": {"asset_type": "branch", "from_bus": 1, "to_bus": 2, "r_pu": 0.1, "x_pu": 0.2},
            "b": {"asset_type": "branch", "from_bus": 2, "to_bus": 3, "r_pu": 0.2, "x_pu": 0.3},
        }
    }


class SemanticBaselineLadderTests(unittest.TestCase):
    def test_component_ladder_separates_attack_families(self) -> None:
        source = fixture()
        expected = {
            "task_asset_drop": (True, False, False),
            "independent_merge": (True, False, False),
            "wrong_one_to_many": (False, False, False),
            "target_id_reuse": (False, False, False),
            "endpoint_parameter_swap": (True, True, False),
            "source_snapshot_mismatch": (True, True, True),
        }
        for family, decisions in expected.items():
            with self.subTest(family=family):
                target, relations, _ = transform(source, family, 0)
                self.assertEqual(global_identity_accepts(source, target, relations), decisions[0])
                self.assertEqual(task_footprint_accepts(source, target, relations), decisions[1])
                self.assertEqual(attribute_invariants_accept(source, target, relations), decisions[2])


if __name__ == "__main__":
    unittest.main()
