from __future__ import annotations

import unittest

import pandas as pd

from validation.run_stage2_full_mapping import map_frames


def asset(asset_id: str, name: str, bus1: str = "", bus2: str = "") -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "canonical_asset_id": asset_id,
        "asset_type": "line",
        "code": "ACLineSegment",
        "name": name,
        "bus1_id": bus1,
        "bus2_id": bus2,
        "terminal_ids": "[]",
        "p_mw": "",
        "q_mvar": "",
        "r": "0.1",
        "x": "0.2",
    }


class FullMappingTests(unittest.TestCase):
    def test_conservative_mapping_taxonomy(self) -> None:
        source = pd.DataFrame(
            [
                asset("a", "exact", "1", "2"),
                asset("b", "old name", "2", "3"),
                asset("c", "id rename", "3", "4"),
                asset("s", "split", "4", "5"),
                asset("drop", "dropped", "5", "6"),
            ]
        )
        target = pd.DataFrame(
            [
                asset("a", "exact", "1", "2"),
                asset("b", "new name", "2", "3"),
                asset("c2", "id rename", "3", "4"),
                asset("s1", "split", "4", "5"),
                asset("s2", "split", "4", "5"),
                asset("create", "created", "6", "7"),
            ]
        )
        rows = pd.DataFrame(map_frames({"case_id": "test"}, source, target))
        counts = rows.mapping_status.value_counts().to_dict()
        self.assertEqual(counts["exact"], 1)
        self.assertEqual(counts["renamed"], 2)
        self.assertEqual(counts["split"], 2)
        self.assertEqual(counts["dropped"], 1)
        self.assertEqual(counts["created"], 1)
        self.assertTrue(
            rows[rows.mapping_status == "split"]
            .adjudication_status.eq("pending_candidate")
            .all()
        )


if __name__ == "__main__":
    unittest.main()
