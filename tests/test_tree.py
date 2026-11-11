"""Kiểm thử Giai đoạn 6: bố cục cây FRS, gợi ý carry-over, sửa cha-con bằng tay (AC-05)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _func import db  # noqa: E402
from _func.frs_tree import build_tree  # noqa: E402
from _func.scan import scan_database  # noqa: E402
from feature import tree as T  # noqa: E402
from test_scan import SAMPLE, make_variant  # noqa: E402

USER_EXAMPLE = ["3B.1.7.0", "3B.1.8.0", "3B.1.9.0", "3B.1.9.1", "3B.1.9.2", "3B.1.8.1", "3B.1.8.2", "3B.1.8.3"]


class Layout(unittest.TestCase):
    def test_ac05_main_branch_horizontal_side_branch_below(self):
        pos, trees = T.layout(build_tree(USER_EXAMPLE))
        # nhánh chính 3B.1.7.0 -> 3B.1.8.0 -> 3B.1.9.0 nằm cùng hàng 0
        self.assertEqual([pos[c] for c in ("3B.1.7.0", "3B.1.8.0", "3B.1.9.0")], [(0, 0), (1, 0), (2, 0)])
        # 3B.1.9.1, 3B.1.9.2 rẽ từ 3B.1.9.0 (không có 3B.1.10.0 nên đi tiếp cùng hàng)
        self.assertEqual([pos[c] for c in ("3B.1.9.1", "3B.1.9.2")], [(3, 0), (4, 0)])
        # nhánh phụ 3B.1.8.1 -> .2 -> .3 rẽ từ 3B.1.8.0 xuống hàng dưới
        self.assertEqual([pos[c] for c in ("3B.1.8.1", "3B.1.8.2", "3B.1.8.3")], [(2, 1), (3, 1), (4, 1)])
        self.assertEqual((trees[0]["root"], trees[0]["rows"], trees[0]["cols"], trees[0]["label"]), ("3B.1.7.0", 2, 5, "3B.1 (LHD)"))

    def test_no_two_nodes_share_a_cell(self):
        codes = USER_EXAMPLE + ["3B.1.10.0", "3B.1.10.1", "3B.1.11.0", "3B.1.9.3", "3B.6.8.0", "3B.6.9.0", "3B.6.8.1", "3A.1.11.0", "3B.8.7.0"]
        pos, trees = T.layout(build_tree(codes))
        self.assertEqual(len(set(pos.values())), len(codes))
        self.assertEqual([t["label"] for t in trees], ["3A.1 (LHD)", "3B.1 (LHD)", "3B.6 (RHD)", "3B.8"])  # segment 8: số thô
        self.assertEqual(sum(t["rows"] for t in trees), max(r for _, r in pos.values()) + 1)
        # mỗi cây chiếm dải hàng riêng
        for t in trees:
            self.assertEqual(pos[t["root"]], (0, t["row_start"]))
        # nhánh chính: 3B.1.9.0 -> 3B.1.10.0 -> 3B.1.11.0 cùng hàng; 3B.1.9.1.. rẽ xuống
        self.assertEqual(pos["3B.1.10.0"][1], pos["3B.1.9.0"][1])
        self.assertEqual(pos["3B.1.11.0"][1], pos["3B.1.9.0"][1])
        self.assertGreater(pos["3B.1.9.1"][1], pos["3B.1.9.0"][1])

    def test_long_chain_does_not_recurse(self):
        codes = [f"3B.1.5.{i}" for i in range(3000)]
        pos, _ = T.layout(build_tree(codes))
        self.assertEqual(pos["3B.1.5.2999"], (2999, 0))


class ProjectTree(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "database"
        fl = self.root / "VF3" / "FL"
        fl.mkdir(parents=True)
        shutil.copy2(SAMPLE, fl / "FRS3B.1.11.0.xlsx")        # ghi chú carry: 3B.1.10.0, 3B.1.10.2, 3B.8.8.0
        for code in ("3B.1.9.0", "3B.1.10.0", "3B.1.10.1", "3B.1.10.2", "3B.1.9.2"):
            make_variant(fl / f"FRS{code}.xlsx", code, 1)
        make_variant(self.root / "VF3" / "RHD" / "FRS3B.6.9.0.xlsx", "3B.6.9.0", 2, side="RHD")
        self.conn = db.open_db(self.tmp / "index.db")
        scan_database(self.conn, self.root)
        self.pid = self.conn.execute("SELECT id FROM project").fetchone()[0]
        self.codes = [r[0] for r in self.conn.execute("SELECT code FROM frs")]

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def tree(self):
        t = T.project_tree(self.conn, self.pid, T.load_metadata(self.root))
        return t, {n["code"]: n for n in t["nodes"]}

    def test_auto_tree(self):
        t, n = self.tree()
        self.assertEqual([x["root"] for x in t["trees"]], ["3B.1.9.0", "3B.6.9.0"])
        self.assertEqual(n["3B.1.11.0"]["parent_code"], "3B.1.10.0")
        self.assertEqual(n["3B.1.10.2"]["parent_code"], "3B.1.10.1")
        self.assertEqual((n["3B.1.9.2"]["parent_code"], n["3B.1.9.2"]["skipped"]), ("3B.1.9.0", ["3B.1.9.1"]))  # thiếu 3B.1.9.1
        self.assertEqual(n["3B.1.9.0"]["parent_id"], None)
        self.assertEqual(n["3B.6.9.0"]["side"], "RHD")
        self.assertEqual((t["rows"], t["cols"]), (4, 4))
        self.assertEqual(n["3B.1.11.0"]["lines"], "FL")
        self.assertIsNone(T.project_tree(self.conn, 9999))

    def test_carry_hints(self):
        _, n = self.tree()
        hints = {h["code"]: h["relation"] for h in n["3B.1.11.0"]["carry"]}
        self.assertEqual(hints["3B.1.10.0"], "ancestor")
        self.assertEqual(hints["3B.1.10.2"], "other_branch")
        self.assertEqual(hints["3B.8.8.0"], "not_indexed")
        self.assertEqual(hints["5C.1.9.0"], "other_project")   # mã FRS của VF5 nhắc trong ghi chú carry-over

    def test_manual_parent_persists_and_wins(self):
        T.set_manual_parent(self.root, "VF3", self.codes, "3B.1.11.0", "3B.1.10.2")
        self.assertTrue((self.root / "_bom_management" / "metadata.json").is_file())
        t, n = self.tree()
        self.assertEqual((n["3B.1.11.0"]["parent_code"], n["3B.1.11.0"]["source"]), ("3B.1.10.2", "manual"))
        self.assertEqual({h["code"]: h["relation"] for h in n["3B.1.11.0"]["carry"]}["3B.1.10.2"], "ancestor")
        self.assertEqual(t["manual_count"], 1)
        # quét lại (kể cả force) không làm mất sửa tay; folder metadata không bị coi là dự án
        report = scan_database(self.conn, self.root, force=True)
        self.assertEqual([p["project"] for p in report["projects"]], ["VF3"])
        self.assertEqual(self.tree()[1]["3B.1.11.0"]["parent_code"], "3B.1.10.2")
        # ép làm gốc, rồi trả về tự động
        T.set_manual_parent(self.root, "VF3", self.codes, "3B.1.11.0", None)
        t, n = self.tree()
        self.assertIsNone(n["3B.1.11.0"]["parent_code"])
        self.assertIn("3B.1.11.0", [x["root"] for x in t["trees"]])
        T.set_manual_parent(self.root, "VF3", self.codes, "3B.1.11.0", "auto")
        self.assertEqual(self.tree()[1]["3B.1.11.0"]["source"], "auto")

    def test_manual_parent_validation(self):
        with self.assertRaisesRegex(ValueError, "chính nó"):
            T.set_manual_parent(self.root, "VF3", self.codes, "3B.1.10.0", "3B.1.10.0")
        with self.assertRaisesRegex(ValueError, "con cháu"):
            T.set_manual_parent(self.root, "VF3", self.codes, "3B.1.10.0", "3B.1.10.2")   # vòng lặp
        with self.assertRaisesRegex(ValueError, "Không có FRS"):
            T.set_manual_parent(self.root, "VF3", self.codes, "3B.1.10.0", "9Z.1.1.1")
        with self.assertRaisesRegex(ValueError, "Không có FRS"):
            T.set_manual_parent(self.root, "VF3", self.codes, "9Z.1.1.1", None)
        self.assertFalse(T.metadata_path(self.root).exists())  # lỗi thì không ghi gì
        # nối khác segment được phép (vd RHD tách ra từ LHD)
        T.set_manual_parent(self.root, "VF3", self.codes, "3B.6.9.0", "3B.1.9.0")
        t, n = self.tree()
        self.assertEqual(n["3B.6.9.0"]["parent_code"], "3B.1.9.0")
        self.assertEqual(len(t["trees"]), 1)
        self.assertEqual(len({(x["col"], x["row"]) for x in t["nodes"]}), len(t["nodes"]))

    def test_stale_manual_parent_falls_back_to_auto(self):
        T.set_manual_parent(self.root, "VF3", self.codes, "3B.1.11.0", "3B.1.10.2")
        (self.root / "VF3" / "FL" / "FRS3B.1.10.2.xlsx").unlink()
        scan_database(self.conn, self.root)
        t, n = self.tree()
        self.assertEqual((n["3B.1.11.0"]["parent_code"], n["3B.1.11.0"]["source"]), ("3B.1.10.0", "auto"))
        self.assertEqual(t["stale_manual"], ["3B.1.11.0"])

    def test_corrupt_metadata_is_ignored(self):
        p = T.metadata_path(self.root)
        p.parent.mkdir(parents=True)
        p.write_text("{hỏng", encoding="utf-8")
        self.assertEqual(self.tree()[1]["3B.1.11.0"]["source"], "auto")


if __name__ == "__main__":
    unittest.main()
