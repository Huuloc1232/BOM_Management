"""Chuẩn hóa text, part number, tên ECU và mã FRS. Chỉ dùng stdlib."""
from __future__ import annotations

import re

# PN Type chuẩn (cột B). Khóa là dạng viết hoa, bỏ khoảng trắng.
PN_TYPE_ALIASES = {
    "HW": "HW",
    "SW": "SW",
    "SW_BASIC": "SW_BASIC",
    "SW_APP": "SW_APP",
    "CAL": "CAL",
    "BOOTLOADER": "BootLoader",
    "BL": "BootLoader",
    "PU": "PU",
    "HMI": "HMI",
    "FONT": "FONT",
    "SW_2-10": "SW_2-10",
    "TBOX": "TBOX",
    "FLDRV": "FL DRV",
    "FLASHDRIVER": "FL DRV",
    "XML": "XML",
}

# DID theo PN Type, lấy từ công thức cột F của template.
DID_BY_PN_TYPE = {
    "HW": "F191",
    "SW": "F188",
    "SW_APP": "F104",
    "SW_BASIC": "F105",
    "BootLoader": "F101",
    "CAL": "F102",
    "HMI": "F106",
    "PU": "F103",
    "SW_2-10": "F198",
    "FONT": "F109",
}

MARKET_ALIASES = {
    "VN": "VN",
    "PHL": "PHL",
    "PHIL": "PHL",
    "LA": "LA",
    "LAO": "LA",
    "LAOS": "LA",
    "INDO": "INDO",
    "IDN": "INDO",
}

# VF PN chuẩn: 3 chữ + 8 số + 2 chữ + '-' + 2 số, vd EEP69080001AD-01
PN_FULL_RE = re.compile(r"^[A-Z]{3}\d{8}[A-Z]{2}-\d{2}$")
PN_BASE_RE = re.compile(r"^[A-Z]{3}\d{8}[A-Z]{2}$")

# Cho phép dính liền sau chữ FRS (tên file FRS3B.1.11.0.xlsx)
FRS_CODE_RE = re.compile(r"(?:(?<![0-9A-Za-z.])|(?<=FRS))([0-9A-Z]{1,3})\.(\d+)\.(\d+)\.(\d+)(?!\d)")
VERSION_RE = re.compile(r"(?:TPV|\bV)\s*(\d+)\b", re.IGNORECASE)
SIDE_RE = re.compile(r"\b(LHD|RHD)\b", re.IGNORECASE)


def norm_text(value) -> str:
    """Chuỗi đã trim, gộp mọi khoảng trắng (kể cả xuống dòng, nbsp) thành 1 dấu cách."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()


def norm_header(value) -> str:
    return norm_text(value).lower()


def norm_pn(value) -> str:
    """PN để so khớp: bỏ mọi khoảng trắng, viết hoa."""
    if value is None:
        return ""
    return re.sub(r"\s+", "", str(value).replace("\xa0", "")).upper()


def split_pn(pn_norm: str) -> tuple[str, str]:
    """Tách (base, rev) tại dấu '-' đầu tiên, giống công thức cột G/I của template."""
    if "-" in pn_norm:
        base, rev = pn_norm.split("-", 1)
        return base, rev
    return pn_norm, ""


def norm_pn_type(value) -> str:
    key = re.sub(r"\s+", "", norm_text(value)).upper()
    return PN_TYPE_ALIASES.get(key, norm_text(value))


def norm_bootloader(value) -> tuple[str, bool]:
    """Mã BootLoader 4 ký tự. Trả (giá trị, was_numeric): số bị Excel bỏ số 0 đầu thì pad lại."""
    if isinstance(value, bool):
        return str(value), False
    if isinstance(value, (int, float)):
        return str(int(value)).zfill(4), True
    text = norm_pn(value)
    return text, False


def norm_market(value) -> str:
    return MARKET_ALIASES.get(norm_text(value).upper(), "")


def variant_market(label: str) -> str:
    """Market của variant xe = token đầu của nhãn (VN FL -> VN, PHL BCO -> PHL)."""
    tokens = norm_text(label).split(" ")
    return norm_market(tokens[0]) if tokens and tokens[0] else ""


def split_ecu_name(raw) -> tuple[str, str, str]:
    """Tách tên ECU có hậu tố: 'MHU VN' / '2IN1 (PHL)' / 'BMS (Low-cost VN)'.

    Trả (ecu_base viết hoa, qualifier nguyên văn, market nếu nhận ra).
    """
    text = norm_text(raw)
    if not text:
        return "", "", ""
    m = re.match(r"^(.*?)\s*\((.*)\)\s*$", text)
    if m:
        base, qual = m.group(1).strip(), m.group(2).strip()
    else:
        parts = text.split(" ", 1)
        base, qual = parts[0], (parts[1].strip() if len(parts) > 1 else "")
    market = ""
    for token in re.split(r"[\s,&/+-]+", qual):
        market = norm_market(token)
        if market:
            break
    return base.upper(), qual, market


def parse_frs_code(text) -> dict | None:
    """Tìm mã FRS đầu tiên trong text. '3B.1.11.0' -> family 3B, seg 1, major 11, minor 0."""
    m = FRS_CODE_RE.search(norm_text(text))
    if not m:
        return None
    family, seg, major, minor = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
    return {
        "code": f"{family}.{seg}.{major}.{minor}",
        "family": family,
        "seg": seg,
        "major": major,
        "minor": minor,
    }


def find_frs_codes(text) -> list[str]:
    return [f"{a}.{int(b)}.{int(c)}.{int(d)}" for a, b, c, d in FRS_CODE_RE.findall(norm_text(text))]


def parse_version(text) -> int | None:
    """Số V/TPV trong text ('... V8 LHD', 'TPV8', 'BOM V8')."""
    cleaned = FRS_CODE_RE.sub(" ", norm_text(text))
    m = VERSION_RE.search(cleaned)
    return int(m.group(1)) if m else None


def parse_side(text) -> str:
    m = SIDE_RE.search(norm_text(text))
    return m.group(1).upper() if m else ""
