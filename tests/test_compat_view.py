"""Kiểm thử Giai đoạn 5: ma trận COM_BOM, câu trả lời nhanh, kiểm tra cặp HW + SW (AC-03)."""
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
from feature.compat_view import check_pair, compat_view  # noqa: E402
from test_scan import SAMPLE  # noqa: E402


class CompatView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        root = cls.tmp / "database"
        (root / "VF3" / "FL").mkdir(parents=True)
        shutil.copy2(SAMPLE, root / "VF3" / "FL" / "FRS3B.1.11.0.xlsx")
        cls.conn = db.open_db(cls.tmp / "index.db")
        scan_database(cls.conn, root)
        cls.fid = cls.conn.execute("SELECT id FROM frs").fetchone()[0]
        cls.v = compat_view(cls.conn, cls.fid)
        cls.g = {g["name"]: g for g in cls.v["groups"]}

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_groups(self):
        self.assertEqual(list(self.g), ["MHU VN", "SS", "ACM", "2IN1 (VN)", "2IN1 (PHL)", "EAC"])
        self.assertEqual(self.v["untracked_ecus"], ["BCM", "CVCLW", "EDS", "EPS", "ABS", "BMS"])
        self.assertIsNone(compat_view(self.conn, 9999))

    def test_acm_matrix(self):
        g = self.g["ACM"]
        self.assertEqual([h["hw_pn"] for h in g["hws"]], ["EEP69080001AA-05", "EEP69080001AB-01", "EEP69080001AD-01"])
        self.assertEqual([s["sw_pn"] for s in g["sws"]], ["SOW69081002AB-01", "SOW69081002AC-02", "SOW69081002AD-01"])
        # mỗi HW chỉ đi với đúng một SW (đường chéo), BL đi kèm
        self.assertEqual(g["cells"], {
            "EEP69080001AA-05|SOW69081002AB-01": "0200",
            "EEP69080001AB-01|SOW69081002AC-02": "0200",
            "EEP69080001AD-01|SOW69081002AD-01": "0201",
        })
        self.assertEqual([h["in_bom"] for h in g["hws"]], [False, False, True])
        self.assertEqual(g["hws"][1]["pu_pns"], ["EEP69081000AE"])  # khoảng trắng đầu đã chuẩn hóa
        self.assertEqual([(x["status"], x["bl_matches"]) for x in g["bom"]], [("ok", True)])

    def test_quick_answer_new_sw_vs_old_hw(self):
        a = self.g["ACM"]["answers"][0]   # SW mới nhất của ACM KHÔNG tương thích hai HW cũ
        self.assertEqual((a["sw"], a["compatible"], a["incompatible"]),
                         ("SOW69081002AD-01", ["EEP69080001AD-01"], ["EEP69080001AA-05", "EEP69080001AB-01"]))
        m = self.g["MHU VN"]["answers"][0]  # SW MHU tương thích cả 5 HW (ô SW merge dọc)
        self.assertEqual((len(m["compatible"]), m["incompatible"]), (5, []))
        t = self.g["2IN1 (VN)"]["answers"][0]
        self.assertEqual((t["sw"], t["compatible"]), ("SOW69272005AA-06", ["EEP69072001AC-02"]))
        self.assertEqual(t["incompatible"], ["EEP69072001AC-01", "EEP69072001HA-01"])

    def test_hw_with_several_sw(self):
        g = self.g["2IN1 (VN)"]
        self.assertIn("EEP69072001AC-01|SOW69272005AA-04", g["cells"])
        self.assertIn("EEP69072001AC-01|SOW69272005AA-05", g["cells"])
        self.assertEqual(len(g["hws"]), 3)   # HW lặp lại ở hai dòng chỉ tính một lần
        self.assertEqual(g["hws"][0]["pu_pns"], ["EEP69072000AD-01"])

    def test_warnings(self):
        ss = self.g["SS"]["bom"][0]
        self.assertEqual((ss["status"], ss["warning"], ss["hw"]), ("hw_not_listed", True, "EEP69031001AE-02"))
        self.assertTrue(self.g["SS"]["warning"])
        # SS: HW của BOM không có trong bảng nhưng SW thì có -> vẫn trả lời được SW đi với HW nào
        self.assertEqual(self.g["SS"]["answers"][0]["compatible"], ["EEP69031001AC-01", "EEP69031001AD-01", "EEP69031001AE-01"])
        self.assertEqual([(o["ecu"], o["variants"]) for o in self.v["orphans"]], [("MHU", ["PHL BCO"])])
        self.assertEqual(self.v["warning_count"], 2)
        # nhóm theo market: 2IN1 (PHL) chỉ nhận block PHL
        self.assertEqual([x["variants"] for x in self.g["2IN1 (PHL)"]["bom"]], [["PHL BCO"]])
        self.assertEqual([x["variants"] for x in self.g["2IN1 (VN)"]["bom"]], [["VN FL", "VN BCO2"]])

    def test_check_pair(self):
        r = check_pair(self.conn, self.fid, "ACM", " eep69080001ad-01 ", "SOW69081002AD-01")
        self.assertEqual((r["compatible"], r["status"], r["matches"][0]["bl_version"]), (True, "ok", "0201"))
        r = check_pair(self.conn, self.fid, "ACM", "EEP69080001AA-05", "SOW69081002AD-01")   # SW mới + HW cũ
        self.assertEqual((r["compatible"], r["status"]), (False, "sw_mismatch"))
        self.assertEqual([x["sw_pn"] for x in r["sw_for_hw"]], ["SOW69081002AB-01"])
        self.assertEqual([x["hw_pn"] for x in r["hw_for_sw"]], ["EEP69080001AD-01"])
        r = check_pair(self.conn, self.fid, "ACM", "EEP69080001ZZ-01", "SOW69081002AD-01")
        self.assertEqual((r["compatible"], r["status"], r["sw_for_hw"]), (False, "hw_not_listed", []))
        # cùng HW/SW nhưng nhóm market khác nhau không lẫn vào nhau
        self.assertFalse(check_pair(self.conn, self.fid, "2IN1 (PHL)", "EEP69072001AC-02", "SOW69272005AA-06")["compatible"])
        self.assertTrue(check_pair(self.conn, self.fid, "2IN1 (VN)", "EEP69072001AC-02", "SOW69272005AA-06")["compatible"])
        self.assertIsNone(check_pair(self.conn, self.fid, "BMS", "x", "y"))


if __name__ == "__main__":
    unittest.main()
