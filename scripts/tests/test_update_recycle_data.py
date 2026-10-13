"""离线验证奖池更新，不依赖网络或改写仓库正文。"""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("recycle_updater", ROOT / "scripts/update-recycle-data.py")
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)
WHEN = updater.parse_time("2026-10-13T12:00:00+08:00")


class RecycleUpdateTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = updater.load_snapshot(updater.ORIGINAL)

    def test_complete_current_materials_and_probabilities(self):
        pools = updater.select_pools(self.snapshot, WHEN)
        normal, special = pools[1]
        self.assertEqual((len(normal), len(special), len(normal.keys() | special.keys())), (44, 27, 50))
        self.assertEqual([sum(r["weight"] for r in p.values()) for p in pools[1]], [10000, 10000])
        self.assertFalse({"30073", "30083", "30093", "30103"} & normal.keys())
        table = updater.render_appendix(self.snapshot, pools)
        self.assertIn("| 紫色 | 提纯源岩 | 40 | 0.40% | 0 | 488 | 4.88% |", table)
        self.assertIn("| 紫色 | 糖聚块 | 4 | 0.04% | 0 | 40 | 0.40% |", table)
        self.assertIn("| 金色 | 重相位对映体 | — | — | — | 168 | 1.68% |", table)

    def test_weight_change_uses_new_total(self):
        changed = copy.deepcopy(self.snapshot)
        rows = changed["data"]["recycleRoomOutputPoolContentDatas"]["itemPool1"]["items"]
        next(r for r in rows if r["itemId"] == "30014")["weight"] = 10040
        old = updater.select_pools(self.snapshot, WHEN)
        new = updater.select_pools(changed, WHEN)
        self.assertFalse(updater.mechanism_changes(self.snapshot, changed, old, new))
        table = updater.render_appendix(changed, new)
        self.assertIn("**20000**、**10000**", table)
        self.assertIn("| 紫色 | 提纯源岩 | 10040 | 50.20% | 0 | 488 | 4.88% |", table)

    def test_duplicate_missing_name_and_invalid_weight(self):
        for defect in ["duplicate", "missing", "weight", "schema"]:
            with self.subTest(defect=defect):
                changed = copy.deepcopy(self.snapshot)
                rows = changed["data"]["recycleRoomOutputPoolContentDatas"]["itemPool1"]["items"]
                if defect == "duplicate":
                    rows.append(copy.deepcopy(rows[0]))
                elif defect == "missing":
                    del changed["items"][rows[0]["itemId"]]
                elif defect == "weight":
                    rows[0]["weight"] = -1
                else:
                    rows[0]["newFilter"] = True
                with self.assertRaises(ValueError):
                    updater.select_pools(changed, WHEN)

    def test_timed_rotation_and_ambiguous_selection(self):
        before = copy.deepcopy(self.snapshot)
        before["selected_at"] = WHEN.isoformat()
        config = before["data"]["recycleRoomOutputPoolDatas"]["itemPool1"]
        config["itemPoolEndTime"] = int(WHEN.timestamp())
        after = copy.deepcopy(before)
        future = WHEN + updater.dt.timedelta(days=1)
        rotated = copy.deepcopy(config)
        rotated["itemPoolId"] = "itemPool2"
        rotated["itemPoolStartTime"] = int(future.timestamp())
        rotated["itemPoolEndTime"] = int(future.timestamp()) + 3600
        after["data"]["recycleRoomOutputPoolDatas"]["itemPool2"] = rotated
        after["data"]["recycleRoomOutputPoolContentDatas"]["itemPool2"] = copy.deepcopy(
            after["data"]["recycleRoomOutputPoolContentDatas"]["itemPool1"])
        self.assertEqual(updater.baseline_pools(before, future)[0]["itemPoolId"], "itemPool1")
        self.assertEqual(updater.select_pools(after, future)[0]["itemPoolId"], "itemPool2")
        rotated["itemPoolStartTime"] = int(WHEN.timestamp())
        with self.assertRaises(ValueError):
            updater.select_pools(after, WHEN)

    def run_isolated(self, candidate, write=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        doc, state, source = root / "doc.md", root / "state.json", root / "candidate.json"
        doc.write_text("---\nupdated: 2026-10-13\n---\n# 测试\n\n" + updater.render_appendix(
            self.snapshot, updater.select_pools(self.snapshot, WHEN)), encoding="utf-8")
        state.write_text(json.dumps(self.snapshot), encoding="utf-8")
        source.write_text(json.dumps(candidate), encoding="utf-8")
        initial = [doc.read_bytes(), state.read_bytes()]
        args = ["--snapshot", str(source), "--as-of", WHEN.isoformat()]
        if write:
            args.append("--write")
        with patch.multiple(updater, ROOT=root, DOC=doc, STATE=state):
            with contextlib.redirect_stdout(io.StringIO()):
                if write and candidate["data"]["recycleRoomConsts"]["recycleBoostSpeed"] != 0.5:
                    with self.assertRaises(ValueError):
                        updater.main(args)
                else:
                    updater.main(args)
                    first = [doc.read_bytes(), state.read_bytes()]
                    updater.main(args)
                    self.assertEqual(first, [doc.read_bytes(), state.read_bytes()])
        return initial, [doc.read_bytes(), state.read_bytes()]

    def test_mechanism_change_keeps_both_files(self):
        changed = copy.deepcopy(self.snapshot)
        changed["data"]["recycleRoomConsts"]["recycleBoostSpeed"] = 0.6
        initial, final = self.run_isolated(changed)
        self.assertEqual(initial, final)

    def test_dry_run_and_repeat_write(self):
        changed = copy.deepcopy(self.snapshot)
        changed["data"]["recycleRoomOutputPoolContentDatas"]["itemPool1"]["items"][0]["weight"] += 100
        initial, final = self.run_isolated(changed, write=False)
        self.assertEqual(initial, final)
        initial, final = self.run_isolated(changed)
        self.assertNotEqual(initial, final)

    def test_score_and_threshold_change_requires_mechanism_review(self):
        for key in ["score", "threshold"]:
            changed = copy.deepcopy(self.snapshot)
            if key == "score":
                changed["data"]["recycleRoomOutputPoolContentDatas"]["itemPool1"]["items"][0]["extraPoolValueChange"] = 1
            else:
                changed["data"]["recycleRoomOutputPoolDatas"]["itemPool1"]["extraPoolRequirement"] = 12000
            self.assertTrue(updater.mechanism_changes(self.snapshot, changed,
                updater.select_pools(self.snapshot, WHEN), updater.select_pools(changed, WHEN)))

    def test_infinite_exchange_material_added_requires_range_review(self):
        changed = copy.deepcopy(self.snapshot)
        rows = changed["data"]["recycleRoomOutputPoolContentDatas"]["itemPool1"]["items"]
        rows.append({"itemId": "30103", "targetTags": ["30103"], "weight": 290,
                     "count": 1, "extraPoolValueChange": 500, "isNew": False})
        blockers = updater.mechanism_changes(self.snapshot, changed,
            updater.select_pools(self.snapshot, WHEN), updater.select_pools(changed, WHEN))
        self.assertTrue(any("产物范围" in b for b in blockers))


if __name__ == "__main__":
    unittest.main()
