"""Kiểm thử Giai đoạn 1 trên docs/sample.xlsx (AC-01, AC-03, AC-04, AC-05)."""
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from _func import normalize as N  # noqa: E402
from _func.compat import compatible_hw_for_sw, is_compatible  # noqa: E402
from _func.frs_tree import build_tree, path_to_root, rule_parent  # noqa: E402
from _func.parse_file import parse_file  # noqa: E402
from _func.parser_change import extract_tickets  # noqa: E402

SAMPLE = ROOT / "docs" / "sample.xlsx"


class SampleBom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = parse_file(SAMPLE)
        cls.blocks = cls.r["blocks"]

    def test_header_info(self):
        self.assertEqual(self.r["frs"]["code"], "3B.1.11.0")
        self.assertEqual((self.r["frs"]["family"], self.r["frs"]["seg"], self.r["frs"]["major"], self.r["frs"]["minor"]), ("3B", 1, 11, 0))
        self.assertEqual(self.r["version"], 8)
        self.assertEqual(self.r["side"], "LHD")

    def test_variants(self):
        self.assertEqual([(v["label"], v["market"]) for v in self.r["variants"]], [("VN FL", "VN"), ("VN BCO2", "VN"), ("PHL BCO", "PHL")])

    def test_ac01_blocks_and_parts(self):
        self.assertEqual(len(self.blocks), 15)
        self.assertEqual(sum(len(b["parts"]) for b in self.blocks), 49)
        self.assertEqual(
            Counter(b["ecu"] for b in self.blocks),
            Counter({"ACM": 1, "BCM": 1, "MHU": 2, "CVCLW": 1, "EDS": 1, "EAC": 1, "EPS": 1, "ABS": 1, "BMS": 3, "2IN1": 2, "SS": 1}),
        )
        cvclw = next(b for b in self.blocks if b["ecu"] == "CVCLW")
        self.assertEqual([p["pn_type"] for p in cvclw["parts"]], ["HW", "SW_BASIC", "SW", "SW_APP", "CAL", "BootLoader"])
        self.assertEqual((cvclw["first_row"], cvclw["last_row"]), (16, 21))

    def test_ac01_recomputed_values_match_file_cache(self):
        self.assertEqual([i for i in self.r["issues"] if i["kind"] == "cache_mismatch"], [])
        acm = self.blocks[0]
        hw = acm["parts"][0]
        self.assertEqual((hw["pn"], hw["pn_base"], hw["rev"], hw["did"], hw["rev_did"]), ("EEP69080001AD-01", "EEP69080001AD", "01", "F191", "F141"))
        self.assertEqual((acm["purchase_pn"], acm["purchase_pn_base"]), ("EEP69081000AF-01", "EEP69081000AF"))
        self.assertEqual(acm["parts"][2]["did"], "F101")

    def test_block_variants_and_labels(self):
        bms = [b for b in self.blocks if b["ecu"] == "BMS"]
        self.assertEqual([b["variants"] for b in bms], [["VN FL"], ["VN BCO2"], ["PHL BCO"]])
        self.assertEqual([b["label"] for b in bms], ["VN FL: BMS (CKD)", "VN BCO2: BMS (Low cost)", "PHL BCO: BMS (Low cost)"])
        # D16: hai block dùng chung HW PN vẫn là hai block riêng
        self.assertEqual(bms[1]["parts"][0]["pn"], bms[2]["parts"][0]["pn"])
        self.assertNotEqual(bms[1]["purchase_pn"], bms[2]["purchase_pn"])
        mhu = [b for b in self.blocks if b["ecu"] == "MHU"]
        self.assertEqual([b["markets"] for b in mhu], [["VN"], ["PHL"]])

    def test_bootloader_numeric_is_padded_string(self):
        boots = {b["ecu"]: p["pn"] for b in self.blocks for p in b["parts"] if p["pn_type"] == "BootLoader"}
        self.assertEqual(boots["CVCLW"], "2422")
        self.assertEqual(boots["ABS"], "1234")
        self.assertEqual(boots["ACM"], "0201")
        self.assertEqual(sum(1 for i in self.r["issues"] if i["kind"] == "bootloader_numeric"), 2)

    def test_ac03_combom(self):
        rows = self.r["com_bom"]
        self.assertEqual(len(rows), 20)
        self.assertEqual(self.r["com_bom_ecus"], ["2IN1", "ACM", "EAC", "MHU", "SS"])
        # SW merge dọc E3:E7: một SW tương thích 5 HW của MHU VN
        mhu_hw = compatible_hw_for_sw(rows, "MHU", "SOW69321131AA-31")
        self.assertEqual(len(mhu_hw), 5)
        self.assertTrue(all(r["market"] == "VN" and r["bl_version"] == "0101" for r in mhu_hw))
        # khoảng trắng đầu ở C12 được chuẩn hóa
        self.assertIn("EEP69081000AE", {r["pu_pn"] for r in rows})

    def test_ac03_compat_warnings(self):
        status = Counter(c["status"] for c in self.r["compat"])
        self.assertEqual(status["ok"], 5)
        self.assertEqual(status["not_tracked"], 8)
        warned = [(c["ecu"], c["variants"]) for c in self.r["compat"] if c["warning"]]
        self.assertEqual(warned, [("MHU", ["PHL BCO"]), ("SS", ["VN FL", "VN BCO2", "PHL BCO"])])

    def test_ac03_is_compatible(self):
        rows = self.r["com_bom"]
        self.assertEqual(is_compatible(rows, "ACM", "EEP69080001AD-01", "SOW69081002AD-01")["status"], "ok")
        self.assertEqual(is_compatible(rows, "ACM", "EEP69080001AA-05", "SOW69081002AD-01")["status"], "sw_mismatch")
        self.assertEqual(is_compatible(rows, "ACM", "EEP69080001ZZ-01", "SOW69081002AD-01")["status"], "hw_not_listed")
        self.assertEqual(is_compatible(rows, "BMS", "BAT69011002AB-01", "SOW69011000AC-06")["status"], "not_tracked")
        # một HW đi với nhiều SW (2IN1 VN: AC-01 với AA-04 và AA-05)
        self.assertEqual(is_compatible(rows, "2IN1", "EEP69072001AC-01", "SOW69272005AA-05", ["VN"])["status"], "ok")

    def test_ac04_change_content(self):
        entries = self.r["change_content"]
        self.assertEqual(self.r["tpvs"], [1, 2, 3, 4, 5, 6, 7, 8])
        self.assertEqual(len(entries), 30)
        self.assertEqual([e["ecu_raw"] for e in entries if e["tpv"] == 3], ["MHU"])  # TPV3 một hàng, không merge
        self.assertEqual(Counter(e["tpv"] for e in entries), Counter({8: 3, 7: 2, 6: 3, 5: 7, 4: 4, 3: 1, 2: 5, 1: 5}))
        # ô nội dung merge dọc: BMS (Low-cost PHL) dùng chung nội dung với BMS (Low-cost VN)
        low = {e["ecu_raw"]: e for e in entries if e["tpv"] == 5 and e["ecu"] == "BMS"}
        self.assertEqual(low["BMS (Low-cost PHL)"]["text"], low["BMS (Low-cost VN)"]["text"])
        self.assertTrue(low["BMS (Low-cost PHL)"]["text_shared_with_row_above"])
        self.assertEqual(low["BMS (Low-cost PHL)"]["market"], "PHL")
        self.assertEqual({e["ecu"] for e in entries if e["ecu_raw"].upper().startswith("2IN1")}, {"2IN1"})

    def test_ac04_tickets(self):
        entries = self.r["change_content"]
        keys = {t["key"] for e in entries for t in e["tickets"]}
        prefixes = Counter(k.rsplit("-", 1)[0] for k in keys)
        self.assertEqual(prefixes["GTSC"], 1)
        self.assertEqual(prefixes["MINIOGREEN"], 1)
        self.assertEqual(prefixes["VF5"], 1)
        self.assertEqual(prefixes["MHU3"], 1)
        self.assertGreater(prefixes["CCB"], 30)
        self.assertGreater(prefixes["VF3"], 100)
        self.assertFalse(any(k.startswith("SOW") for k in keys))  # không khớp nhầm part number
        where = sorted((e["tpv"], e["ecu"]) for e in entries if any(t["key"] == "CCB-26107" for t in e["tickets"]))
        self.assertEqual(where, [(5, "MHU"), (6, "MHU")])
        t = next(t for e in entries for t in e["tickets"] if t["key"] == "GTSC-7888")
        self.assertEqual(t["url"], "https://tms.vinfast.vn/browse/GTSC-7888")

    def test_carry_notes(self):
        notes = [n for e in self.r["change_content"] for n in e["carry_notes"]]
        codes = {c for n in notes for c in n["frs_codes"]}
        self.assertTrue({"3B.1.10.2", "3B.8.8.0", "3B.1.10.0"} <= codes)

    def test_no_errors(self):
        self.assertTrue(self.r["ok"])
        self.assertEqual([i for i in self.r["issues"] if i["severity"] == "error"], [])


class Normalize(unittest.TestCase):
    def test_pn(self):
        self.assertEqual(N.norm_pn(" eep69081000AE-02 "), "EEP69081000AE-02")
        self.assertEqual(N.norm_pn("SOW690740 03AA-01"), "SOW69074003AA-01")
        self.assertEqual(N.split_pn("EEP69081000AE-02"), ("EEP69081000AE", "02"))
        self.assertIsNone(N.PN_FULL_RE.match("EEP69081000A"))

    def test_frs_code(self):
        self.assertEqual(N.parse_frs_code("FRS 3B.1.11.0 V8 LHD\nHW SW BOM")["code"], "3B.1.11.0")
        self.assertEqual(N.parse_frs_code("FRS3B.1.11.0.xlsx")["code"], "3B.1.11.0")
        self.assertEqual(N.parse_frs_code("FRS BA.1.9.4 EBUS")["family"], "BA")
        self.assertEqual(N.parse_version("FRS 3B.1.11.0 V8 LHD"), 8)
        self.assertEqual(N.parse_version("VF3 FRS 3B.1.11.0 BOM V8"), 8)
        self.assertEqual(N.parse_version("TPV12"), 12)
        self.assertIsNone(N.parse_version("FRS 3B.1.11.0"))

    def test_ecu_names(self):
        self.assertEqual(N.split_ecu_name("MHU VN"), ("MHU", "VN", "VN"))
        self.assertEqual(N.split_ecu_name("2IN1 (PHL)"), ("2IN1", "PHL", "PHL"))
        self.assertEqual(N.split_ecu_name("BMS (Low-cost VN)"), ("BMS", "Low-cost VN", "VN"))
        self.assertEqual(N.split_ecu_name("BCM "), ("BCM", "", ""))
        self.assertEqual(N.split_ecu_name("2in1"), ("2IN1", "", ""))

    def test_ticket_formats(self):
        text = "[CCB-22560] Remote - VinFast TMS\nGTSC-7888] VF 3\nCCB-9228\tCCB-10245 Sub-task\nSOW69011004AD-05\nVF3RHD-12 x VF3-21485\t[FRS 3B.1.9.3 V1]"
        self.assertEqual([t["key"] for t in extract_tickets(text)], ["CCB-22560", "GTSC-7888", "CCB-9228", "CCB-10245", "VF3RHD-12", "VF3-21485"])


class FrsTree(unittest.TestCase):
    def test_rule_parent(self):
        self.assertEqual(rule_parent("3B.1.9.2"), "3B.1.9.1")
        self.assertEqual(rule_parent("3B.1.9.0"), "3B.1.8.0")
        self.assertEqual(rule_parent("3B.1.8.1"), "3B.1.8.0")
        self.assertIsNone(rule_parent("3B.1.0.0"))

    def test_ac05_user_example(self):
        codes = ["3B.1.7.0", "3B.1.8.0", "3B.1.9.0", "3B.1.9.1", "3B.1.9.2", "3B.1.8.1", "3B.1.8.2", "3B.1.8.3"]
        tree = build_tree(codes)
        self.assertEqual(tree["roots"], ["3B.1.7.0"])  # D18: không có 3B.1.6.0 nên là gốc
        self.assertEqual(tree["nodes"]["3B.1.8.0"]["children"], ["3B.1.8.1", "3B.1.9.0"])
        self.assertEqual(path_to_root(tree, "3B.1.9.2"), ["3B.1.7.0", "3B.1.8.0", "3B.1.9.0", "3B.1.9.1", "3B.1.9.2"])
        self.assertEqual(path_to_root(tree, "3B.1.8.3"), ["3B.1.7.0", "3B.1.8.0", "3B.1.8.1", "3B.1.8.2", "3B.1.8.3"])

    def test_lhd_rhd_are_separate_trees(self):
        tree = build_tree(["3B.1.8.0", "3B.1.9.0", "3B.6.8.0", "3B.6.9.0"])
        self.assertEqual(tree["roots"], ["3B.1.8.0", "3B.6.8.0"])

    def test_missing_parent_links_to_nearest_ancestor(self):
        tree = build_tree(["3B.1.8.0", "3B.1.9.2"])
        node = tree["nodes"]["3B.1.9.2"]
        self.assertEqual(node["parent"], "3B.1.8.0")
        self.assertEqual(node["skipped"], ["3B.1.9.1", "3B.1.9.0"])

    def test_manual_override_wins(self):
        tree = build_tree(["3B.1.8.0", "3B.1.8.1", "3B.1.9.0"], manual={"3B.1.9.0": "3B.1.8.1"})
        self.assertEqual(tree["nodes"]["3B.1.9.0"]["parent"], "3B.1.8.1")
        self.assertEqual(tree["nodes"]["3B.1.9.0"]["source"], "manual")


if __name__ == "__main__":
    unittest.main()
