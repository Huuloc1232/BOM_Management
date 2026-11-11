"""Kiểm thử Giai đoạn 2: quét thư mục, chọn TPV cuối, quét gia tăng, chỉ mục SQLite."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from _func import db, metadata  # noqa: E402
from _func.scan import filename_line_hint, infer_line, scan_database  # noqa: E402

SAMPLE = ROOT / "docs" / "sample.xlsx"


def make_variant(dst: Path, code: str, version: int, side: str = "LHD", edits: dict | None = None):
    """Tạo file BOM mới từ sample: đổi mã FRS, số V và vài ô. Lưu bằng openpyxl nên
    các ô công thức KHÔNG còn giá trị cache (giống file chưa từng được Excel tính lại)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(SAMPLE)
    ws = wb.worksheets[0]
    ws["A1"] = f"FRS {code} V{version} {side}\nHW SW BOM"
    ws.title = f"VF3 FRS {code} BOM V{version}"
    wb["Change content "]["A1"] = f"FRS {code}"
    wb["Change content "]["A3"] = f"TPV{version}"
    for cell, value in (edits or {}).items():
        ws[cell] = value
    wb.save(dst)
    wb.close()


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.root = self.tmp / "database"
        self.conn = db.open_db(self.tmp / "index.db")
        fl = self.root / "VF3" / "FL"
        fl.mkdir(parents=True)
        shutil.copy2(SAMPLE, fl / "FRS3B.1.11.0.xlsx")
        make_variant(fl / "FRS3B.1.11.0_V7.xlsx", "3B.1.11.0", 7)
        make_variant(fl / "FRS3B.1.10.0.xlsx", "3B.1.10.0", 5, edits={"C5": "SOW69081002AC-02"})
        make_variant(self.root / "VF3" / "Legacy" / "RHD" / "FRS3A.6.10.0.xlsx", "3A.6.10.0", 3, side="RHD")
        make_variant(self.root / "ECVan" / "FRSEV.1.2.0.xlsx", "EV.1.2.0", 1)
        (self.root / "VF3" / "FL" / "~$FRS3B.1.11.0.xlsx").write_bytes(b"lock")
        (self.root / "_output").mkdir()
        wb = openpyxl.Workbook()
        wb.active["A1"] = "ghi chú"
        wb.save(self.root / "VF3" / "notes.xlsx")

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def scan(self, **kw):
        return scan_database(self.conn, self.root, **kw)

    def project(self, report, name):
        return next(p for p in report["projects"] if p["project"] == name)

    def test_first_scan(self):
        report = self.scan()
        self.assertEqual([p["project"] for p in report["projects"]], ["ECVan", "VF3"])
        vf3 = self.project(report, "VF3")
        self.assertEqual(vf3["files"], 5)  # bỏ file tạm ~$ của Excel
        self.assertEqual(sorted((i["frs"], i["version"]) for i in vf3["imported"]), [("3A.6.10.0", 3), ("3B.1.10.0", 5), ("3B.1.11.0", 8)])
        # AC-06: V7 và V8 của cùng FRS, chỉ V8 được dùng
        self.assertEqual([(i["file"], i["version"]) for i in vf3["ignored"]], [("FL/FRS3B.1.11.0_V7.xlsx", 7)])
        self.assertEqual([i["file"] for i in vf3["not_bom"]], ["notes.xlsx"])
        self.assertEqual(vf3["errors"], [])
        c = report["counts"]
        self.assertEqual((c["project"], c["frs"], c["ecu_block"], c["part"]), (2, 4, 60, 196))

    def test_lines_from_folders(self):
        self.scan()
        rows = self.conn.execute(
            "SELECT p.name, l.path, (SELECT path FROM line WHERE id=l.parent_id) AS parent FROM line l JOIN project p ON p.id=l.project_id ORDER BY 1, 2"
        ).fetchall()
        self.assertEqual([tuple(r) for r in rows], [("VF3", "FL", None), ("VF3", "Legacy", None), ("VF3", "Legacy/RHD", "Legacy")])
        frs_lines = dict(self.conn.execute("SELECT f.code, l.path FROM frs f JOIN frs_line fl ON fl.frs_id=f.id JOIN line l ON l.id=fl.line_id").fetchall())
        self.assertEqual(frs_lines, {"3B.1.11.0": "FL", "3B.1.10.0": "FL", "3A.6.10.0": "Legacy/RHD"})
        side = dict(self.conn.execute("SELECT code, side FROM frs").fetchall())
        self.assertEqual(side["3A.6.10.0"], "RHD")

    def test_file_without_formula_cache_still_parses(self):
        self.scan()
        row = self.conn.execute(
            "SELECT p.pn, p.pn_base, p.rev, p.did FROM part p JOIN frs f ON f.id=p.frs_id JOIN ecu_block b ON b.id=p.block_id WHERE f.code='3B.1.10.0' AND b.ecu='ACM' AND p.pn_type='SW'"
        ).fetchone()
        self.assertEqual(tuple(row), ("SOW69081002AC-02", "SOW69081002AC", "02", "F188"))

    def test_incremental_scan_parses_nothing(self):
        self.scan()
        report = self.scan()
        for p in report["projects"]:
            self.assertEqual(p["parsed"], 0)
            self.assertEqual(p["imported"], [])
        self.assertEqual(report["counts"]["frs"], 4)

    def test_touch_without_content_change_is_not_reparsed(self):
        self.scan()
        path = self.root / "VF3" / "FL" / "FRS3B.1.11.0.xlsx"
        os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 100))
        vf3 = self.project(self.scan(), "VF3")
        self.assertEqual((vf3["parsed"], vf3["imported"]), (0, []))

    def test_new_version_replaces_and_reports_diff(self):
        self.scan()
        make_variant(self.root / "VF3" / "FL" / "FRS3B.1.11.0_new.xlsx", "3B.1.11.0", 9, edits={"C5": "SOW69081002AE-01"})
        vf3 = self.project(self.scan(), "VF3")
        self.assertEqual(len(vf3["imported"]), 1)
        imp = vf3["imported"][0]
        self.assertEqual((imp["frs"], imp["version"], imp["action"]), ("3B.1.11.0", 9, "updated"))
        self.assertEqual([(d["ecu"], d["pn_type"], d["pn"]) for d in imp["diff"]["removed"]], [("ACM", "SW", "SOW69081002AD-01")])
        self.assertEqual([(d["ecu"], d["pn_type"], d["pn"]) for d in imp["diff"]["added"]], [("ACM", "SW", "SOW69081002AE-01")])
        self.assertEqual(sorted(i["version"] for i in vf3["ignored"]), [7, 8])
        self.assertEqual(self.conn.execute("SELECT version FROM frs WHERE code='3B.1.11.0'").fetchone()[0], 9)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM frs").fetchone()[0], 4)
        log = self.conn.execute("SELECT action, old_version, new_version FROM import_log WHERE frs_code='3B.1.11.0' ORDER BY id DESC").fetchone()
        self.assertEqual(tuple(log), ("updated", 8, 9))
        # compat: SW mới không có trong COM_BOM cho HW này
        status = self.conn.execute("SELECT compat_status FROM ecu_block b JOIN frs f ON f.id=b.frs_id WHERE f.code='3B.1.11.0' AND b.ecu='ACM'").fetchone()[0]
        self.assertEqual(status, "sw_mismatch")

    def test_deleted_files(self):
        self.scan()
        (self.root / "VF3" / "FL" / "FRS3B.1.11.0.xlsx").unlink()        # còn V7 -> lùi về V7
        (self.root / "VF3" / "Legacy" / "RHD" / "FRS3A.6.10.0.xlsx").unlink()  # không còn file -> xóa FRS
        shutil.rmtree(self.root / "ECVan")                               # xóa cả dự án
        report = self.scan()
        vf3 = self.project(report, "VF3")
        self.assertEqual([(i["frs"], i["version"]) for i in vf3["imported"]], [("3B.1.11.0", 7)])
        self.assertEqual([i["frs"] for i in vf3["removed"]], ["3A.6.10.0"])
        self.assertEqual([r[0] for r in self.conn.execute("SELECT name FROM project")], ["VF3"])
        # folder Legacy/RHD vẫn còn nên line vẫn còn (line rỗng); xóa folder thì line tự dọn
        self.assertEqual([r[0] for r in self.conn.execute("SELECT path FROM line ORDER BY 1")], ["FL", "Legacy", "Legacy/RHD"])
        shutil.rmtree(self.root / "VF3" / "Legacy")
        self.scan()
        self.assertEqual([r[0] for r in self.conn.execute("SELECT path FROM line ORDER BY 1")], ["FL"])
        self.assertEqual(report["counts"]["frs"], 2)

    def test_manual_line_link_survives_reimport(self):
        (self.root / "VF3" / "Pin LFP").mkdir()
        self.scan()
        metadata.set_frs_lines(self.root, "VF3", "3B.1.11.0", ["Pin LFP", "Khong ton tai"])
        report = self.scan(force=True)
        lines = dict(self.conn.execute("SELECT l.path, fl.source FROM frs f JOIN frs_line fl ON fl.frs_id=f.id JOIN line l ON l.id=fl.line_id WHERE f.code='3B.1.11.0'").fetchall())
        self.assertEqual(lines, {"FL": "auto", "Pin LFP": "manual"})  # D4: một FRS thuộc nhiều line
        self.assertEqual(report["stale_lines"], [{"project": "VF3", "frs": "3B.1.11.0", "line": "Khong ton tai"}])
        metadata.set_frs_lines(self.root, "VF3", "3B.1.11.0", [])
        self.scan()
        self.assertEqual([r[0] for r in self.conn.execute("SELECT l.path FROM frs f JOIN frs_line fl ON fl.frs_id=f.id JOIN line l ON l.id=fl.line_id WHERE f.code='3B.1.11.0'")], ["FL"])

    def test_manual_frs_placeholder_lifecycle(self):
        self.scan()
        code = metadata.add_manual_frs(self.root, "VF3", "frs 3b.1.12.0", ["FL"])
        self.assertEqual(code, "3B.1.12.0")
        self.scan()
        row = self.conn.execute("SELECT manual, version, side, file_id FROM frs WHERE code='3B.1.12.0'").fetchone()
        self.assertEqual(tuple(row), (1, None, "LHD", None))
        self.assertEqual([r[0] for r in self.conn.execute("SELECT l.path FROM frs f JOIN frs_line fl ON fl.frs_id=f.id JOIN line l ON l.id=fl.line_id WHERE f.code='3B.1.12.0'")], ["FL"])
        self.scan(force=True)                       # quét lại không xóa FRS tạo tay
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM frs WHERE code='3B.1.12.0'").fetchone()[0], 1)
        with self.assertRaisesRegex(ValueError, "đã được tạo tay"):
            metadata.add_manual_frs(self.root, "VF3", "3B.1.12.0", [])
        for bad in ("", "abc", "3B.1.12", "3B.1.12.0.1", "3B.1.12.0 V2"):
            with self.assertRaises(ValueError, msg=bad):
                metadata.add_manual_frs(self.root, "VF3", bad, [])
        # có file thật cho mã đó: FRS thật thay thế, là FRS "mới", vẫn giữ line gán tay
        make_variant(self.root / "VF3" / "Legacy" / "RHD" / "FRS3B.1.12.0.xlsx", "3B.1.12.0", 1)
        vf3 = self.project(self.scan(), "VF3")
        self.assertEqual([(i["frs"], i["action"]) for i in vf3["imported"]], [("3B.1.12.0", "new")])
        row = self.conn.execute("SELECT manual, version FROM frs WHERE code='3B.1.12.0'").fetchone()
        self.assertEqual(tuple(row), (0, 1))
        lines = dict(self.conn.execute("SELECT l.path, fl.source FROM frs f JOIN frs_line fl ON fl.frs_id=f.id JOIN line l ON l.id=fl.line_id WHERE f.code='3B.1.12.0'").fetchall())
        self.assertEqual(lines, {"FL": "manual", "Legacy/RHD": "auto"})
        # xóa file: quay lại là FRS tạo tay; xóa khỏi metadata: biến mất
        (self.root / "VF3" / "Legacy" / "RHD" / "FRS3B.1.12.0.xlsx").unlink()
        self.scan()
        self.assertEqual(self.conn.execute("SELECT manual FROM frs WHERE code='3B.1.12.0'").fetchone()[0], 1)
        metadata.remove_manual_frs(self.root, "VF3", "3B.1.12.0")
        self.scan()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM frs WHERE code='3B.1.12.0'").fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, "không phải FRS tạo tay"):
            metadata.remove_manual_frs(self.root, "VF3", "3B.1.11.0")

    def test_same_frs_in_two_line_folders_links_both_lines(self):
        self.scan()
        dst = self.root / "VF3" / "FL Plus" / "FRS3B.1.11.0.xlsx"
        dst.parent.mkdir()
        shutil.copy2(SAMPLE, dst)
        vf3 = self.project(self.scan(), "VF3")
        self.assertTrue(any(i["same_version"] for i in vf3["ignored"]))
        lines = sorted(r[0] for r in self.conn.execute("SELECT l.path FROM frs f JOIN frs_line fl ON fl.frs_id=f.id JOIN line l ON l.id=fl.line_id WHERE f.code='3B.1.11.0'"))
        self.assertEqual(lines, ["FL", "FL Plus"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM frs WHERE code='3B.1.11.0'").fetchone()[0], 1)

    def test_where_used_one_row_per_block(self):
        self.scan()
        rows = [r for r in db.where_used(self.conn, "BAT69011016AA-01") if r["frs"] == "3B.1.11.0"]
        self.assertEqual([(r["ecu"], r["variants"], r["label"]) for r in rows], [("BMS", "VN BCO2", "VN BCO2: BMS (Low cost)"), ("BMS", "PHL BCO", "PHL BCO: BMS (Low cost)")])
        self.assertEqual(rows[0]["lines"], "FL")
        # tìm không kèm rev và có khoảng trắng thừa; Purchase PN cũng tra được
        self.assertTrue(db.where_used(self.conn, " bat69011016aa "))
        pu = [r for r in db.where_used(self.conn, "EEP69081000AF") if r["frs"] == "3B.1.11.0"]
        self.assertEqual([(r["ecu"], r["pn_type"]) for r in pu], [("ACM", "PU")])
        # PN xuất hiện ở nhiều FRS và nhiều dự án
        self.assertEqual(len({(r["project"], r["frs"]) for r in db.where_used(self.conn, "EEP69080001AD-01")}), 4)

    def test_ticket_lookup(self):
        self.scan()
        rows = [r for r in db.ticket_lookup(self.conn, "ccb-26107") if r["frs"] == "3B.1.11.0"]
        self.assertEqual([(r["tpv"], r["ecu"]) for r in rows], [(6, "MHU"), (5, "MHU")])

    def test_quality_issues_stored(self):
        self.scan()
        kinds = {r[0] for r in self.conn.execute("SELECT DISTINCT kind FROM quality_issue")}
        self.assertTrue({"bootloader_numeric", "compat_hw_not_listed", "compat_no_market_rows", "purchase_equals_hw"} <= kinds)

    def test_single_project_flat_folder(self):
        flat = self.tmp / "sample"
        flat.mkdir()
        shutil.copy2(SAMPLE, flat / "VF3_FACELIFT_VN_FRS3B.1.11.0_HWSW BOM_V8.xlsx")
        conn = db.open_db(self.tmp / "flat.db")
        report = scan_database(conn, flat, single_project="VF3")
        self.assertEqual(report["projects"][0]["imported"][0]["line"], "FACELIFT VN")
        conn.close()


class LineInference(unittest.TestCase):
    def test_filename_hint(self):
        self.assertEqual(filename_line_hint("FRS3B.1.11.0", "VF3"), "")
        self.assertEqual(filename_line_hint("VF3_FACELIFT_VN_FRS3B.1.11.0_HWSW BOM_V8", "VF3"), "FACELIFT VN")

    def test_folder_and_filename(self):
        self.assertEqual(infer_line(Path("Legacy/LHD/FRS3A.1.11.0.xlsx"), "VF3"), (["Legacy", "LHD"], ""))
        self.assertEqual(infer_line(Path("FL/VF3_FL_FRS3B.1.11.0.xlsx"), "VF3"), (["FL"], ""))
        segments, conflict = infer_line(Path("FL/VF3_LEGACY_FRS3A.1.11.0.xlsx"), "VF3")
        self.assertEqual(segments, ["FL"])
        self.assertIn("LEGACY", conflict)


if __name__ == "__main__":
    unittest.main()
