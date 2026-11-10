"""Kiểm thử Giai đoạn 4: so sánh hai FRS theo part number, tra cứu ticket hai chiều (AC-04, AC-07)."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _func import db  # noqa: E402
from _func.scan import scan_database  # noqa: E402
from feature.compare import compare_blocks, compare_frs, frs_list, frs_tickets, pair_blocks  # noqa: E402
from test_scan import SAMPLE, make_variant  # noqa: E402


def blk(ecu, variants, label="", **parts):
    return {"ecu": ecu, "variants": variants, "label": label, "parts": {k: v if isinstance(v, list) else [v] for k, v in parts.items()}}


class PairAndDiff(unittest.TestCase):
    def test_pairs_by_variant_even_when_order_differs(self):
        a = [blk("BMS", ["VN FL"], HW="BAT69011002AB-01"), blk("BMS", ["PHL BCO"], HW="BAT69011016AA-01")]
        b = [blk("BMS", ["PHL BCO"], HW="BAT69011016AA-02"), blk("BMS", ["VN FL"], HW="BAT69011002AB-01")]
        pairs = pair_blocks(a, b)
        self.assertEqual([(x["variants"], y["variants"]) for x, y in pairs], [(["VN FL"], ["VN FL"]), (["PHL BCO"], ["PHL BCO"])])

    def test_unmatched_blocks_are_one_sided(self):
        a = [blk("MHU", ["VN FL"], HW="EEP69321151HA-01"), blk("XGW", ["VN FL"], HW="EEP69000001AA-01")]
        b = [blk("MHU", ["VN FL"], HW="EEP69321151HA-01"), blk("MHU", ["PHL BCO"], HW="EEP69321001AC-01")]
        r = compare_blocks(a, b)
        self.assertEqual([(g["ecu"], g["block"]) for g in r["groups"]], [("MHU", "both"), ("MHU", "only_b"), ("XGW", "only_a")])
        self.assertEqual((r["summary"]["same"], r["summary"]["added"], r["summary"]["removed"]), (1, 1, 1))

    def test_different_variant_names_still_pair_by_hw(self):
        # Legacy và Facelift đặt tên variant khác nhau: ghép theo HW/PU
        a = [blk("BMS", ["Base VN"], HW="BAT69011002AB-01"), blk("BMS", ["Base PHL"], HW="BAT69011016AA-01")]
        b = [blk("BMS", ["PHL BCO"], HW="BAT69011016AA-03"), blk("BMS", ["VN FL"], HW="BAT69011002AB-02")]
        self.assertEqual([(x["variants"], y["variants"]) for x, y in pair_blocks(a, b)], [(["Base VN"], ["VN FL"]), (["Base PHL"], ["PHL BCO"])])

    def test_status_kinds(self):
        a = [blk("ACM", ["VN"], PU="EEP69081000AF-01", HW="EEP69080001AD-01", SW="SOW69081002AD-01", BootLoader="0201", CAL="SOW69081009AA-01")]
        b = [blk("ACM", ["VN"], PU="EEP69081000AF-01", HW="EEP69080001AD-02", SW="SOW69081099AA-01", BootLoader="0201", SW_APP="SOW69081005AA-01")]
        rows = {r["pn_type"]: r["status"] for r in compare_blocks(a, b)["groups"][0]["rows"]}
        self.assertEqual(rows, {"PU": "same", "HW": "rev", "SW": "changed", "SW_APP": "added", "CAL": "removed", "BootLoader": "same"})
        self.assertEqual([r["pn_type"] for r in compare_blocks(a, b)["groups"][0]["rows"]], ["PU", "HW", "SW", "SW_APP", "CAL", "BootLoader"])


class CompareOnIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        root = cls.tmp / "database"
        (root / "VF3" / "FL").mkdir(parents=True)
        shutil.copy2(SAMPLE, root / "VF3" / "FL" / "FRS3B.1.11.0.xlsx")
        make_variant(root / "VF3" / "FL" / "FRS3B.1.10.0.xlsx", "3B.1.10.0", 5, edits={
            "C5": "SOW69081002AC-02",      # ACM SW: đổi rev lẫn hậu tố -> khác PN
            "C7": "EEP69010002AC-01",      # BCM HW: chỉ đổi rev
            "K22": "PWT69093000AC-03",     # EDS Purchase PN
            "C21": "2421",                 # CVCLW BootLoader
        })
        make_variant(root / "VF3" / "FL" / "FRS3B.1.10.1.xlsx", "3B.1.10.1", 2)
        make_variant(root / "VF3" / "FL" / "FRS3B.1.9.0.xlsx", "3B.1.9.0", 9)
        cls.conn = db.open_db(cls.tmp / "index.db")
        scan_database(cls.conn, root)
        cls.ids = dict(cls.conn.execute("SELECT code, id FROM frs").fetchall())

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_ac07_compare_part_numbers(self):
        r = compare_frs(self.conn, self.ids["3B.1.10.0"], self.ids["3B.1.11.0"])
        self.assertEqual((r["a"]["code"], r["b"]["code"]), ("3B.1.10.0", "3B.1.11.0"))
        self.assertEqual(len(r["groups"]), 15)
        self.assertTrue(all(g["block"] == "both" for g in r["groups"]))
        diffs = [(g["ecu"], x["pn_type"], x["a"], x["b"], x["status"]) for g in r["groups"] for x in g["rows"] if x["status"] != "same"]
        self.assertEqual(diffs, [
            ("ACM", "SW", "SOW69081002AC-02", "SOW69081002AD-01", "changed"),
            ("BCM", "HW", "EEP69010002AC-01", "EEP69010002AC-02", "rev"),
            ("CVCLW", "BootLoader", "2421", "2422", "changed"),
            ("EDS", "PU", "PWT69093000AC-03", "PWT69093000AD-04", "changed"),
        ])
        self.assertEqual(r["summary"], {"same": 60, "rev": 1, "changed": 3, "added": 0, "removed": 0})
        self.assertEqual(sum(1 for g in r["groups"] if g["differs"]), 4)

    def test_compare_identical_and_missing(self):
        r = compare_frs(self.conn, self.ids["3B.1.11.0"], self.ids["3B.1.10.1"])
        self.assertEqual(r["summary"]["same"], 64)
        self.assertFalse(any(g["differs"] for g in r["groups"]))
        self.assertIsNone(compare_frs(self.conn, self.ids["3B.1.11.0"], 9999))

    def test_frs_tickets_grouped(self):
        tickets = frs_tickets(self.conn, self.ids["3B.1.11.0"])
        keys = [t["key"] for t in tickets]
        self.assertEqual(len(keys), len(set(keys)))
        t = next(t for t in tickets if t["key"] == "CCB-26107")
        self.assertEqual((t["tpvs"], t["ecus"], t["first_tpv"]), ([6, 5], ["MHU"], 5))
        self.assertEqual(t["url"], "https://tms.vinfast.vn/browse/CCB-26107")
        self.assertEqual(tickets[0]["first_tpv"], 8)  # mới nhất ở trên
        prefixes = {t["prefix"] for t in tickets}
        self.assertEqual(prefixes, {"CCB", "VF3", "VF5", "GTSC", "MINIOGREEN", "MHU3"})

    def test_ticket_diff_between_frs(self):
        # 3B.1.10.0 lấy từ sample nhưng TPV8 bị ghi thành TPV5 -> cùng tập ticket
        r = compare_frs(self.conn, self.ids["3B.1.10.0"], self.ids["3B.1.11.0"])
        self.assertEqual((r["tickets"]["only_a"], r["tickets"]["only_b"]), ([], []))
        self.assertGreater(r["tickets"]["common"], 150)

    def test_frs_list_suggests_parent(self):
        items = {f["code"]: f for f in frs_list(self.conn)}
        self.assertEqual(items["3B.1.10.1"]["parent_code"], "3B.1.10.0")
        self.assertEqual(items["3B.1.11.0"]["parent_code"], "3B.1.10.0")
        self.assertEqual(items["3B.1.10.0"]["parent_id"], self.ids["3B.1.9.0"])
        self.assertIsNone(items["3B.1.9.0"]["parent_id"])  # gốc cây


if __name__ == "__main__":
    unittest.main()
