"""Kiểm thử Giai đoạn 3: server web và API (FR-01..FR-05, FR-22..FR-26)."""
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app import App, bind_server  # noqa: E402
from test_scan import SAMPLE, make_variant  # noqa: E402


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.root = cls.tmp / "database"
        (cls.root / "VF3" / "FL").mkdir(parents=True)
        shutil.copy2(SAMPLE, cls.root / "VF3" / "FL" / "FRS3B.1.11.0.xlsx")
        make_variant(cls.root / "VF3" / "FL" / "FRS3B.1.10.0.xlsx", "3B.1.10.0", 5, edits={"C5": "SOW69081002AC-02"})
        make_variant(cls.root / "VF3" / "Legacy" / "RHD" / "FRS3A.6.10.0.xlsx", "3A.6.10.0", 3, side="RHD")
        cls.app = App(db_path=cls.tmp / "index.db", settings_path=cls.tmp / "settings.json")
        cls.server = bind_server(cls.app, 18110)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        cls.post("/api/settings", {"root": str(cls.root)})

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def call(cls, path, body=None, headers=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{cls.port}{path}", data=data, headers=headers or {})
        try:
            with cls.opener.open(req, timeout=30) as res:
                return res.status, res.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    @classmethod
    def get(cls, path):
        status, raw = cls.call(path)
        return status, json.loads(raw)

    @classmethod
    def post(cls, path, body, headers=None):
        status, raw = cls.call(path, body, headers)
        return status, json.loads(raw)

    def frs_id(self, code):
        _, d = self.get("/api/search?q=" + quote(code))
        return next(f["id"] for f in d["frs"] if f["code"] == code)

    def test_pages_and_assets(self):
        status, raw = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(b"BOM Management", raw)
        self.assertEqual(self.call("/assets/app.js")[0], 200)
        self.assertEqual(self.call("/assets/app.css")[0], 200)
        self.assertEqual(self.call("/assets/../app.py")[0], 404)       # không lộ file ngoài assets
        self.assertEqual(self.call("/assets/%2e%2e/app.py")[0], 404)

    def test_state_and_project(self):
        _, s = self.get("/api/state")
        self.assertIn("VF3", [p["name"] for p in s["projects"]])
        vf3 = next(p for p in s["projects"] if p["name"] == "VF3")
        self.assertEqual((vf3["frs_count"], vf3["ecu_count"]), (3, 11))
        self.assertEqual(s["filters"]["variants"], ["PHL BCO", "VN BCO2", "VN FL"])
        _, p = self.get(f"/api/project/{vf3['id']}")
        self.assertTrue({"FL", "Legacy", "Legacy/RHD"} <= {l["path"] for l in p["lines"]})
        self.assertEqual([f["code"] for f in p["frs"]], ["3A.6.10.0", "3B.1.10.0", "3B.1.11.0"])
        self.assertEqual(self.get("/api/project/999")[0], 404)

    def test_frs_detail(self):
        status, d = self.get(f"/api/frs/{self.frs_id('3B.1.11.0')}")
        self.assertEqual(status, 200)
        self.assertEqual((d["frs"]["code"], d["frs"]["version"], d["frs"]["side"], d["frs"]["lines"]), ("3B.1.11.0", 8, "LHD", "FL"))
        self.assertEqual(len(d["blocks"]), 15)
        self.assertEqual(sum(len(b["parts"]) for b in d["blocks"]), 49)
        self.assertEqual(len(d["com_bom"]), 20)
        self.assertEqual(sorted({c["tpv"] for c in d["changes"]}), [1, 2, 3, 4, 5, 6, 7, 8])
        warned = [b["ecu"] for b in d["blocks"] if b["compat_status"] in ("hw_not_listed", "sw_mismatch", "no_market_rows")]
        self.assertEqual(warned, ["MHU", "SS"])
        phl = next(v["id"] for v in d["variants"] if v["label"] == "PHL BCO")
        self.assertEqual(len([b for b in d["blocks"] if phl in b["variant_ids"]]), 11)
        self.assertEqual(self.get("/api/frs/999")[0], 404)

    def test_search_part_number(self):
        _, d = self.get("/api/search?q=" + quote(" bat69011016aa "))
        self.assertEqual(len(d["parts"]), 6)                      # 2 block x 3 FRS, mỗi block một dòng (D16)
        self.assertEqual({p["ecu"] for p in d["parts"]}, {"BMS"})
        _, d = self.get("/api/search?q=BAT69011016AA-01&variant=" + quote("PHL BCO"))
        self.assertEqual({p["variants"] for p in d["parts"]}, {"PHL BCO"})
        _, d = self.get("/api/search?q=EEP69081000AF")            # Purchase PN, không gõ rev
        self.assertEqual({(p["ecu"], p["pn_type"]) for p in d["parts"]}, {("ACM", "PU")})
        _, d = self.get("/api/search?q=SOW69081002AC-02")         # PN chỉ có ở FRS 3B.1.10.0
        self.assertEqual([(p["frs"], p["ecu"], p["pn_type"]) for p in d["parts"]], [("3B.1.10.0", "ACM", "SW")])
        _, d = self.get("/api/search?q=EEP6908&pn_type=HW")
        self.assertTrue(d["parts"] and all(p["pn_type"] == "HW" for p in d["parts"]))

    def test_search_frs_ecu_ticket(self):
        _, d = self.get("/api/search?q=" + quote("FRS 3B.1.11"))
        self.assertEqual([f["code"] for f in d["frs"]], ["3B.1.11.0"])
        _, d = self.get("/api/search?q=mhu")
        self.assertEqual(len(d["ecus"]), 6)
        self.assertEqual({e["ecu"] for e in d["ecus"]}, {"MHU"})
        _, d = self.get("/api/search?q=ccb-26107")
        self.assertEqual({t["key"] for t in d["tickets"]}, {"CCB-26107"})
        self.assertEqual(d["tickets"][0]["url"], "https://tms.vinfast.vn/browse/CCB-26107")
        self.assertEqual(d["parts"], [])
        _, d = self.get("/api/search?q=" + quote("100%_'\" OR 1=1 --"))   # ký tự đặc biệt không gây lỗi
        self.assertEqual((d["frs"], d["parts"], d["ecus"], d["tickets"]), ([], [], [], []))
        _, d = self.get("/api/search?q=")
        self.assertEqual(d["parts"], [])

    def test_add_project_and_line(self):
        status, _ = self.post("/api/projects", {"name": "ECVan"})
        self.assertEqual(status, 200)
        self.assertTrue((self.root / "ECVan").is_dir())
        self.assertEqual(self.post("/api/projects", {"name": "ECVan"})[0], 409)
        for bad in ("", "a/b", "..", "_x", "x:y", ".hidden"):
            self.assertEqual(self.post("/api/projects", {"name": bad})[0], 400, bad)
        _, s = self.get("/api/state")
        pid = next(p["id"] for p in s["projects"] if p["name"] == "VF3")
        self.assertEqual(self.post("/api/lines", {"project_id": pid, "parent_path": "Legacy", "name": "LHD"})[0], 200)
        self.assertTrue((self.root / "VF3" / "Legacy" / "LHD").is_dir())
        _, p = self.get(f"/api/project/{pid}")
        self.assertIn("Legacy/LHD", [l["path"] for l in p["lines"]])
        self.assertEqual(self.post("/api/lines", {"project_id": pid, "parent_path": "../..", "name": "x"})[0], 400)
        self.assertEqual(self.post("/api/lines", {"project_id": pid, "parent_path": "KhongCo", "name": "x"})[0], 400)
        self.assertFalse((self.tmp / "x").exists())

    def test_write_api_rejects_other_origins(self):
        self.assertEqual(self.post("/api/scan", {}, {"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.call("/api/state", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.post("/api/scan", {}, {"Origin": f"http://127.0.0.1:{self.port}"})[0], 200)

    def test_bad_root(self):
        status, d = self.post("/api/settings", {"root": str(self.tmp / "khong-co")})
        self.assertEqual(status, 400)
        self.assertIn("không tồn tại", d["error"])
        self.assertEqual(self.get("/api/state")[1]["root"], str(self.root))  # cài đặt cũ không bị ghi đè


if __name__ == "__main__":
    unittest.main()
