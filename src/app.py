"""BOM Management - web tool local (Python stdlib http.server + SQLite).

Chạy:  python src/app.py [--root <thư mục database>] [--port 8010] [--open]
Chỉ lắng nghe 127.0.0.1. File Excel chỉ được đọc, không bao giờ bị sửa.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

from _func import db  # noqa: E402
from _func.scan import SKIP_DIR_PREFIXES, scan_database  # noqa: E402
from feature import compare, compat_view, queries  # noqa: E402
from feature import tree as frs_tree_view  # noqa: E402

DEFAULT_PORT = 8010  # 8000 đã dùng cho Abbreviation Web
ASSETS = SRC / "assets"
INVALID_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class App:
    def __init__(self, db_path=None, settings_path=None, root=None):
        self.db_path = Path(db_path) if db_path else db.default_db_path()
        self.settings_path = Path(settings_path) if settings_path else self.db_path.parent / "settings.json"
        self.scan_lock = threading.Lock()
        self.settings = self._load_settings()
        if root:
            self.settings["root"] = str(Path(root))
            self._save_settings()
        db.open_db(self.db_path).close()  # tạo schema

    # ----- settings -----
    def _load_settings(self) -> dict:
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"root": ""}

    def _save_settings(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.settings_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.settings_path)  # ghi nguyên tử

    @property
    def root(self) -> Path | None:
        return Path(self.settings["root"]) if self.settings.get("root") else None

    def conn(self):
        return db.open_db(self.db_path)

    # ----- hành động -----
    def set_root(self, root: str) -> dict:
        path = Path(root.strip().strip('"'))
        if not path.is_dir():
            raise ApiError(400, f"Thư mục không tồn tại: {path}")
        self.settings["root"] = str(path)
        self._save_settings()
        return self.scan()

    def scan(self, force: bool = False) -> dict:
        if self.root is None:
            raise ApiError(400, "Chưa chọn thư mục database")
        if not self.root.is_dir():
            raise ApiError(400, f"Thư mục database không tồn tại: {self.root}")
        if not self.scan_lock.acquire(blocking=False):
            raise ApiError(409, "Đang quét, vui lòng đợi")
        try:
            conn = self.conn()
            try:
                return scan_database(conn, self.root, force=force)
            finally:
                conn.close()
        finally:
            self.scan_lock.release()

    def metadata(self) -> dict:
        return frs_tree_view.load_metadata(self.root) if self.root else {"projects": {}}

    def set_parent(self, project_id: int, code: str, parent) -> dict:
        """Sửa tay quan hệ cha-con giữa hai FRS (FR-36); lưu vào metadata.json trong thư mục database."""
        if self.root is None:
            raise ApiError(400, "Chưa chọn thư mục database")
        conn = self.conn()
        try:
            row = conn.execute("SELECT name FROM project WHERE id=?", (project_id,)).fetchone()
            if row is None:
                raise ApiError(404, "Không tìm thấy dự án")
            codes = [r[0] for r in conn.execute("SELECT code FROM frs WHERE project_id=?", (project_id,))]
            try:
                frs_tree_view.set_manual_parent(self.root, row["name"], codes, code, parent)
            except ValueError as e:
                raise ApiError(400, str(e))
            return frs_tree_view.project_tree(conn, project_id, self.metadata())
        finally:
            conn.close()

    @staticmethod
    def _check_name(name: str) -> str:
        name = (name or "").strip()
        if not name or INVALID_NAME.search(name) or name in (".", "..") or name.startswith(SKIP_DIR_PREFIXES) or name.endswith((".", " ")):
            raise ApiError(400, "Tên không hợp lệ (không dùng \\ / : * ? \" < > | và không bắt đầu bằng . _ ~)")
        return name

    def add_project(self, name: str) -> dict:
        """Dự án = một folder trong thư mục database (FR-02)."""
        if self.root is None:
            raise ApiError(400, "Chưa chọn thư mục database")
        target = self.root / self._check_name(name)
        if target.exists():
            raise ApiError(409, f"Đã có dự án '{target.name}'")
        target.mkdir()
        return self.scan()

    def add_line(self, project_id: int, parent_path: str, name: str) -> dict:
        """Line = folder con trong folder dự án; line con = folder lồng nhau (FR-03)."""
        conn = self.conn()
        try:
            row = conn.execute("SELECT root_dir FROM project WHERE id=?", (project_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise ApiError(404, "Không tìm thấy dự án")
        base = Path(row["root_dir"])
        parent = base
        for seg in [s for s in (parent_path or "").split("/") if s]:
            parent = parent / self._check_name(seg)
        if not parent.is_dir():
            raise ApiError(400, "Line cha không tồn tại")
        target = parent / self._check_name(name)
        if target.exists():
            raise ApiError(409, f"Đã có line '{target.name}'")
        target.mkdir()
        return self.scan()


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BOMManagement/0.3"

        def log_message(self, fmt, *args):  # im lặng, tránh spam console
            pass

        # ----- tiện ích -----
        def _send(self, status: int, body: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status: int = 200):
            self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _local_only(self):
            """Chặn trang web khác gọi API ghi (CSRF / DNS rebinding)."""
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                raise ApiError(403, "Chỉ chấp nhận truy cập từ máy này")
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
                raise ApiError(403, "Origin không hợp lệ")

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                raise ApiError(413, "Dữ liệu quá lớn")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                raise ApiError(400, "JSON không hợp lệ")
            if not isinstance(data, dict):
                raise ApiError(400, "JSON không hợp lệ")
            return data

        def _static(self, rel: str):
            path = (ASSETS / rel).resolve()
            if ASSETS.resolve() not in path.parents or not path.is_file():
                raise ApiError(404, "Không tìm thấy")
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript",):
                ctype += "; charset=utf-8"
            self._send(200, path.read_bytes(), ctype)

        # ----- GET -----
        def do_GET(self):
            try:
                self._local_only()
                url = urlparse(self.path)
                qs = {k: v[0] for k, v in parse_qs(url.query).items()}
                path = url.path
                if path in ("/", "/index.html"):
                    return self._send(200, (SRC / "index.html").read_bytes(), "text/html; charset=utf-8")
                if path.startswith("/assets/"):
                    return self._static(path[len("/assets/"):])
                if not path.startswith("/api/"):
                    raise ApiError(404, "Không tìm thấy")
                conn = app.conn()
                try:
                    if path == "/api/state":
                        data = queries.state(conn)
                        data["root"] = app.settings.get("root", "")
                        data["scanning"] = app.scan_lock.locked()
                        data["filters"] = queries.filter_options(conn)
                        return self._json(data)
                    m = re.fullmatch(r"/api/project/(\d+)", path)
                    if m:
                        data = queries.project_detail(conn, int(m.group(1)))
                        if data is None:
                            raise ApiError(404, "Không tìm thấy dự án")
                        return self._json(data)
                    m = re.fullmatch(r"/api/project/(\d+)/tree", path)
                    if m:
                        data = frs_tree_view.project_tree(conn, int(m.group(1)), app.metadata())
                        if data is None:
                            raise ApiError(404, "Không tìm thấy dự án")
                        return self._json(data)
                    m = re.fullmatch(r"/api/frs/(\d+)", path)
                    if m:
                        data = queries.frs_detail(conn, int(m.group(1)))
                        if data is None:
                            raise ApiError(404, "Không tìm thấy FRS")
                        return self._json(data)
                    m = re.fullmatch(r"/api/frs/(\d+)/tickets", path)
                    if m:
                        return self._json({"tickets": compare.frs_tickets(conn, int(m.group(1)))})
                    m = re.fullmatch(r"/api/frs/(\d+)/compat", path)
                    if m:
                        data = compat_view.compat_view(conn, int(m.group(1)))
                        if data is None:
                            raise ApiError(404, "Không tìm thấy FRS")
                        return self._json(data)
                    m = re.fullmatch(r"/api/frs/(\d+)/compat-check", path)
                    if m:
                        if not qs.get("hw") or not qs.get("sw"):
                            raise ApiError(400, "Cần nhập cả HW PN và SW PN")
                        data = compat_view.check_pair(conn, int(m.group(1)), qs.get("group", ""), qs["hw"], qs["sw"])
                        if data is None:
                            raise ApiError(404, "ECU này không có trong COM_BOM của FRS")
                        return self._json(data)
                    if path == "/api/frs-list":
                        return self._json({"frs": compare.frs_list(conn, app.metadata())})
                    if path == "/api/compare":
                        try:
                            a, b = int(qs.get("a", "")), int(qs.get("b", ""))
                        except ValueError:
                            raise ApiError(400, "Cần chọn hai FRS để so sánh")
                        data = compare.compare_frs(conn, a, b)
                        if data is None:
                            raise ApiError(404, "Không tìm thấy FRS")
                        return self._json(data)
                    if path == "/api/search":
                        return self._json(queries.search(conn, qs.get("q", ""), qs))
                finally:
                    conn.close()
                raise ApiError(404, "Không tìm thấy")
            except ApiError as e:
                self._json({"error": e.message}, e.status)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:  # lỗi không lường trước: trả JSON thay vì treo kết nối
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        # ----- POST -----
        def do_POST(self):
            try:
                self._local_only()
                path = urlparse(self.path).path
                body = self._body()
                if path == "/api/settings":
                    return self._json(app.set_root(str(body.get("root", ""))))
                if path == "/api/scan":
                    return self._json(app.scan(force=bool(body.get("force"))))
                if path == "/api/projects":
                    return self._json(app.add_project(str(body.get("name", ""))))
                if path == "/api/lines":
                    return self._json(app.add_line(int(body.get("project_id") or 0), str(body.get("parent_path", "")), str(body.get("name", ""))))
                if path == "/api/tree/parent":
                    parent = body.get("parent")
                    if parent is not None and not isinstance(parent, str):
                        raise ApiError(400, "Giá trị cha không hợp lệ")
                    return self._json(app.set_parent(int(body.get("project_id") or 0), str(body.get("code", "")), parent))
                raise ApiError(404, "Không tìm thấy")
            except ApiError as e:
                self._json({"error": e.message}, e.status)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    return Handler


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows: SO_REUSEADDR cho phép hai tiến trình cùng bind một cổng, nên phải tắt.
    # Linux/macOS: bật để khởi động lại ngay không bị kẹt cổng ở trạng thái TIME_WAIT.
    allow_reuse_address = os.name != "nt"


def bind_server(app: App, preferred: int, tries: int = 20) -> ThreadingHTTPServer:
    """Mở server ở cổng ưu tiên, bận thì thử các cổng kế tiếp."""
    for port in range(preferred, preferred + tries):
        try:
            return _Server(("127.0.0.1", port), make_handler(app))
        except OSError:
            continue
    raise SystemExit(f"Không tìm được cổng trống trong khoảng {preferred}-{preferred + tries - 1}")


def already_running(url: str) -> bool:
    import urllib.request

    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # không đi qua proxy công ty
        with opener.open(url + "api/state", timeout=1.5) as res:
            return "projects" in json.loads(res.read().decode("utf-8"))
    except Exception:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BOM Management web tool (local)")
    ap.add_argument("--root", help="Thư mục database (mỗi folder con là một dự án)")
    ap.add_argument("--db", help="File chỉ mục SQLite")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--open", action="store_true", help="Mở trình duyệt sau khi khởi động")
    args = ap.parse_args(argv)

    running = f"http://127.0.0.1:{args.port}/"
    if already_running(running):  # bấm launcher lần hai: mở lại tab thay vì chạy thêm server
        print(f"BOM Management đã chạy sẵn tại {running}")
        if args.open:
            webbrowser.open(running)
        return 0
    app = App(db_path=args.db, root=args.root)
    server = bind_server(app, args.port)
    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    print(f"BOM Management đang chạy tại {url}  (Ctrl+C để dừng)")
    print(f"Thư mục database: {app.settings.get('root') or '(chưa chọn, đặt trong giao diện)'}")
    print(f"Chỉ mục: {app.db_path}")
    if app.root and app.root.is_dir():
        threading.Thread(target=lambda: _safe_scan(app), daemon=True).start()  # quét gia tăng khi khởi động
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _safe_scan(app: App) -> None:
    try:
        app.scan()
    except Exception as e:  # không để lỗi quét làm chết server
        print(f"Quét khi khởi động thất bại: {e}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
