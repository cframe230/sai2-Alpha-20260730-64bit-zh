#!/usr/bin/env python3
"""Build a Simplified Chinese resource patch for PaintTool SAI 2 2026.07.30.

The program code is not modified.  This script replaces strings in the built-in
Japanese locale with Chinese strings.  When copied beside a SAI installation,
it updates that installation's sai2.exe in place and keeps the .bak rollback
copy untouched.  In the development repository it still writes an independent
output folder.  License files and third-party executable patches are not edited.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def first_existing(*paths: Path | None) -> Path | None:
    """Return the first existing path, preserving a useful fallback path."""
    for path in paths:
        if path is not None and path.exists():
            return path
    return next((path for path in paths if path is not None), None)


# When the script is copied beside the SAI files shown in the user's folder
# layout, use that folder as the package root.  In the development repository
# it remains under tools/, so the original repository layout continues to work.
LOCAL_PACKAGE = (
    SCRIPT_DIR
    if (SCRIPT_DIR / "sai2.exe.1785683660.bak").exists()
    and (SCRIPT_DIR / "sai2.ini").exists()
    else None
)
ROOT = LOCAL_PACKAGE or REPO_ROOT

if LOCAL_PACKAGE is not None:
    NEW_ORIGINAL = LOCAL_PACKAGE / "sai2.exe.1785683660.bak"
    OFFICIAL_PACKAGE = LOCAL_PACKAGE
    # The portable layout is intentionally updated in place.  The .bak file
    # remains the immutable source/rollback copy.
    default_output = LOCAL_PACKAGE
else:
    NEW_ORIGINAL = ROOT / "Sai2_2026" / "sai2.exe.1785683660.bak"
    OFFICIAL_PACKAGE = ROOT / "Sai2_2026"
    default_output = ROOT / "Sai2_2026_简体中文"
OUTPUT = Path(os.environ["SAI2_ZH_OUTPUT"]) if os.environ.get("SAI2_ZH_OUTPUT") else default_output

README_TEMPLATE = first_existing(
    SCRIPT_DIR / "汉化说明模板.txt",
    REPO_ROOT / "tools" / "汉化说明模板.txt",
)
TRANSLATION_JSON = first_existing(
    SCRIPT_DIR / "translation.json",
    REPO_ROOT / "tools" / "translation.json",
)

EXPECTED_HASHES = {
    "2026.07.30 original": "11E5FCAA495F4859B772FE2BAF3C83C8522CE12F991950A97C849A237DAAC805",
}

# Raw file offsets and record counts.  Each locale record is three uint64s:
# numeric id, UTF-16 key pointer, UTF-16 value pointer.
NEW_JA_GROUPS = [(0x385ED8, 1471), (0x38E8D8, 247), (0x39C198, 14), (0x3AB3F8, 18), (0x3B3208, 101), (0x3CEFE8, 73)]
NEW_EN_GROUPS = [(0x390018, 1471), (0x398A18, 217), (0x399E88, 3), (0x399EE8, 25), (0x3AB5C8, 18), (0x3B3B98, 101), (0x3CF6D8, 73)]
UI_FONT_NAME = "Microsoft YaHei UI"
UI_FONT_REFERENCES = [
    # raw instruction offset, instruction RVA, expected opcode, original target RVA
    (0x234877, 0x235477, b"\x48\x8D\x3D", 0x3CCA08),  # Meiryo UI
    (0x23487E, 0x23547E, b"\x48\x8D\x05", 0x3CC9E8),  # MS UI Gothic
]

KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}\Z")
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


class PEImage:
    def __init__(self, path: Path):
        self.path = path
        self.data = bytearray(path.read_bytes())
        if self.data[:2] != b"MZ":
            raise ValueError(f"Not a PE file: {path}")
        self.pe_offset = struct.unpack_from("<I", self.data, 0x3C)[0]
        if self.data[self.pe_offset:self.pe_offset + 4] != b"PE\0\0":
            raise ValueError(f"Invalid PE signature: {path}")
        number_of_sections = struct.unpack_from("<H", self.data, self.pe_offset + 6)[0]
        optional_size = struct.unpack_from("<H", self.data, self.pe_offset + 20)[0]
        self.number_of_sections_offset = self.pe_offset + 6
        self.number_of_sections = number_of_sections
        self.optional_offset = self.pe_offset + 24
        magic = struct.unpack_from("<H", self.data, self.optional_offset)[0]
        if magic != 0x20B:
            raise ValueError("Only 64-bit PE32+ files are supported")
        self.image_base = struct.unpack_from("<Q", self.data, self.optional_offset + 24)[0]
        self.checksum_offset = self.optional_offset + 64
        section_offset = self.optional_offset + optional_size
        self.section_table_offset = section_offset
        self.sections = []
        for index in range(number_of_sections):
            off = section_offset + index * 40
            name = bytes(self.data[off:off + 8]).rstrip(b"\0").decode("ascii", "replace")
            virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", self.data, off + 8)
            self.sections.append((name, rva, virtual_size, raw_offset, raw_size))

    @staticmethod
    def _align(value: int, alignment: int) -> int:
        return (value + alignment - 1) // alignment * alignment

    def add_readonly_data_section(self, name: bytes, payload: bytes) -> int:
        if not 1 <= len(name) <= 8:
            raise ValueError("PE section name must contain 1 to 8 bytes")
        file_alignment = struct.unpack_from("<I", self.data, self.optional_offset + 36)[0]
        section_alignment = struct.unpack_from("<I", self.data, self.optional_offset + 32)[0]
        size_of_headers = struct.unpack_from("<I", self.data, self.optional_offset + 60)[0]
        header_offset = self.section_table_offset + self.number_of_sections * 40
        if header_offset + 40 > size_of_headers:
            raise ValueError("No room for another PE section header")
        if any(self.data[header_offset:header_offset + 40]):
            raise ValueError("The next PE section header slot is not empty")

        last_end = max(rva + max(virtual_size, raw_size) for _n, rva, virtual_size, _o, raw_size in self.sections)
        new_rva = self._align(last_end, section_alignment)
        new_raw_offset = self._align(len(self.data), file_alignment)
        new_raw_size = self._align(len(payload), file_alignment)
        if new_raw_offset > len(self.data):
            self.data.extend(b"\0" * (new_raw_offset - len(self.data)))
        self.data.extend(payload)
        self.data.extend(b"\0" * (new_raw_size - len(payload)))

        characteristics = 0x40000040  # IMAGE_SCN_CNT_INITIALIZED_DATA | IMAGE_SCN_MEM_READ
        section_header = struct.pack(
            "<8sIIIIIIHHI",
            name.ljust(8, b"\0"), len(payload), new_rva, new_raw_size, new_raw_offset,
            0, 0, 0, 0, characteristics,
        )
        self.data[header_offset:header_offset + 40] = section_header
        self.number_of_sections += 1
        struct.pack_into("<H", self.data, self.number_of_sections_offset, self.number_of_sections)
        initialized_size = struct.unpack_from("<I", self.data, self.optional_offset + 8)[0]
        struct.pack_into("<I", self.data, self.optional_offset + 8, initialized_size + new_raw_size)
        size_of_image = self._align(new_rva + len(payload), section_alignment)
        struct.pack_into("<I", self.data, self.optional_offset + 56, size_of_image)
        self.sections.append((name.decode("ascii"), new_rva, len(payload), new_raw_offset, new_raw_size))
        return new_rva

    def va_to_offset(self, va: int) -> int:
        rva = va - self.image_base
        for _name, section_rva, virtual_size, raw_offset, raw_size in self.sections:
            if section_rva <= rva < section_rva + max(virtual_size, raw_size):
                result = raw_offset + rva - section_rva
                if not 0 <= result < len(self.data):
                    break
                return result
        raise ValueError(f"VA 0x{va:X} is outside mapped sections")

    def utf16(self, va: int, limit: int = 16384) -> tuple[str, int]:
        off = self.va_to_offset(va)
        end = off
        while end + 1 < len(self.data) and end - off < limit:
            if self.data[end:end + 2] == b"\0\0":
                return bytes(self.data[off:end]).decode("utf-16le"), off
            end += 2
        raise ValueError(f"Unterminated UTF-16 string at VA 0x{va:X}")

    def records(self, groups: list[tuple[int, int]]) -> list[dict]:
        result = []
        for start, count in groups:
            for index in range(count):
                off = start + index * 24
                ident, key_va, value_va = struct.unpack_from("<QQQ", self.data, off)
                key, _ = self.utf16(key_va)
                value, value_off = self.utf16(value_va)
                if not KEY_RE.fullmatch(key):
                    raise ValueError(f"Invalid locale key at 0x{off:X}: {key!r}")
                result.append({
                    "record_offset": off,
                    "id": ident,
                    "key": key,
                    "value": value,
                    "value_va": value_va,
                    "value_offset": value_off,
                })
        return result


def load_translation_memory(records: list[dict]) -> list[str]:
    """Load and validate the complete translation.json for this exact build."""
    if TRANSLATION_JSON is None or not TRANSLATION_JSON.exists():
        raise FileNotFoundError(
            f"找不到 {TRANSLATION_JSON or 'translation.json'}；没有翻译库时不会运行。"
        )
    try:
        data = json.loads(TRANSLATION_JSON.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取翻译库 {TRANSLATION_JSON}。") from exc
    if not isinstance(data, dict) or data.get("source_sha256") != EXPECTED_HASHES["2026.07.30 original"]:
        raise ValueError("translation.json 不是 2026.07.30 对应的翻译库。")
    items = data.get("translations")
    if not isinstance(items, list) or len(items) != len(records):
        raise ValueError(
            f"translation.json 词条数量不匹配：需要 {len(records)} 条，实际 {len(items) if isinstance(items, list) else 0} 条。"
        )
    targets = []
    for index, (record, item) in enumerate(zip(records, items), start=1):
        if not isinstance(item, dict):
            raise ValueError(f"translation.json 第 {index} 条格式错误。")
        if item.get("key") != record["key"] or item.get("ja") != record["value"]:
            raise ValueError(f"translation.json 第 {index} 条与当前 sai2.exe 不匹配。")
        target = item.get("zh_cn")
        if not isinstance(target, str) or not target:
            raise ValueError(f"translation.json 第 {index} 条缺少 zh_cn 翻译。")
        targets.append(target)
    return targets


def build_translation_inputs():
    if not NEW_ORIGINAL or not NEW_ORIGINAL.exists():
        raise FileNotFoundError("找不到 2026.07.30 原版备份 sai2.exe.1785683660.bak")
    if not OFFICIAL_PACKAGE or not OFFICIAL_PACKAGE.exists():
        raise FileNotFoundError("找不到 SAI2 文件夹或官方文件包")
    new_original = PEImage(NEW_ORIGINAL)
    new_ja = new_original.records(NEW_JA_GROUPS)
    new_en = new_original.records(NEW_EN_GROUPS)
    targets = load_translation_memory(new_ja)
    return new_original, new_ja, new_en, targets


def calculate_pe_checksum(data: bytearray, checksum_offset: int) -> int:
    temp = bytearray(data)
    temp[checksum_offset:checksum_offset + 4] = b"\0\0\0\0"
    total = 0
    length = len(temp)
    for offset in range(0, length - 1, 2):
        total += temp[offset] | (temp[offset + 1] << 8)
        total = (total & 0xFFFF) + (total >> 16)
    if length & 1:
        total += temp[-1]
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + length) & 0xFFFFFFFF


def write_executable(path: Path, data: bytes) -> None:
    try:
        path.write_bytes(data)
    except PermissionError as exc:
        raise RuntimeError(f"无法写入 {path}；请先完全退出 SAI2 后再运行脚本。") from exc


def main() -> int:
    for path, expected in [(NEW_ORIGINAL, EXPECTED_HASHES["2026.07.30 original"])] :
        if path is None or not path.exists():
            raise FileNotFoundError(path or "2026.07.30 原版备份")
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"Unexpected source hash for {path}: {actual}")

    image, records, _english_records, translation_targets = build_translation_inputs()

    proposals = []
    for record, target in zip(records, translation_targets):
        source = record["value"]
        item = {**record, "translation": target, "origin": "translation.json"}
        proposals.append(item)

    changed = [proposal for proposal in proposals if proposal["translation"] != proposal["value"]]
    unique_targets = list(dict.fromkeys(proposal["translation"] for proposal in changed))
    section_strings = unique_targets + ([UI_FONT_NAME] if UI_FONT_NAME not in unique_targets else [])

    original_data = bytes(image.data)
    original_length = len(original_data)
    string_payload = bytearray()
    string_offsets: dict[str, int] = {}
    for target in section_strings:
        string_offsets[target] = len(string_payload)
        string_payload.extend(target.encode("utf-16le") + b"\0\0")
    new_section_rva = image.add_readonly_data_section(b".zhcn", bytes(string_payload))

    allowed_ranges = [
        (image.number_of_sections_offset, image.number_of_sections_offset + 2),
        (image.optional_offset + 8, image.optional_offset + 12),
        (image.optional_offset + 56, image.optional_offset + 60),
        (image.section_table_offset + (image.number_of_sections - 1) * 40,
         image.section_table_offset + image.number_of_sections * 40),
    ]
    for proposal in changed:
        pointer_offset = proposal["record_offset"] + 16
        target_va = image.image_base + new_section_rva + string_offsets[proposal["translation"]]
        struct.pack_into("<Q", image.data, pointer_offset, target_va)
        allowed_ranges.append((pointer_offset, pointer_offset + 8))

    font_va = image.image_base + new_section_rva + string_offsets[UI_FONT_NAME]
    for raw_offset, instruction_rva, opcode, expected_target_rva in UI_FONT_REFERENCES:
        if bytes(image.data[raw_offset:raw_offset + 3]) != opcode:
            raise ValueError(f"Unexpected UI font reference opcode at 0x{raw_offset:X}")
        old_displacement = struct.unpack_from("<i", image.data, raw_offset + 3)[0]
        old_target_rva = instruction_rva + 7 + old_displacement
        if old_target_rva != expected_target_rva:
            raise ValueError(f"Unexpected UI font target at 0x{raw_offset:X}: 0x{old_target_rva:X}")
        new_displacement = font_va - (image.image_base + instruction_rva + 7)
        struct.pack_into("<i", image.data, raw_offset + 3, new_displacement)
        allowed_ranges.append((raw_offset + 3, raw_offset + 7))

    struct.pack_into("<I", image.data, image.checksum_offset, 0)
    checksum = calculate_pe_checksum(image.data, image.checksum_offset)
    struct.pack_into("<I", image.data, image.checksum_offset, checksum)
    allowed_ranges.append((image.checksum_offset, image.checksum_offset + 4))

    for index, (before, after) in enumerate(zip(original_data, image.data[:original_length])):
        if before != after and not any(start <= index < end for start, end in allowed_ranges):
            raise AssertionError(f"Unexpected modified byte at file offset 0x{index:X}")

    in_place = OUTPUT.resolve() == OFFICIAL_PACKAGE.resolve()
    if in_place:
        # Build and validate in memory first; only now replace the executable.
        write_executable(OUTPUT / "sai2.exe", image.data)
    else:
        if OUTPUT.exists():
            shutil.rmtree(OUTPUT)
        shutil.copytree(OFFICIAL_PACKAGE, OUTPUT)
        write_executable(OUTPUT / "sai2.exe", image.data)
    if README_TEMPLATE and README_TEMPLATE.exists():
        shutil.copy2(README_TEMPLATE, OUTPUT / "汉化说明.txt")
    else:
        (OUTPUT / "汉化说明.txt").write_text(
            "PaintTool SAI 2 2026.07.30 简体中文补丁\n"
            "本补丁仅替换界面文字和界面字体，原版备份为 sai2.exe.1785683660.bak。\n",
            encoding="utf-8",
        )
    ini_path = OUTPUT / "sai2.ini"
    if ini_path.exists():
        ini_bytes = ini_path.read_bytes()
        ini_encoding = "utf-16" if ini_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        ini = ini_bytes.decode(ini_encoding)
        ini = re.sub(r"(?m)^lang\s*=\s*en\s*$", "lang = ja", ini, count=1)
        ini_path.write_text(ini, encoding=ini_encoding, newline="\r\n")

    output_sha256 = sha256(OUTPUT / "sai2.exe")
    print(f"Built: {OUTPUT}")
    print(f"Patched locale records: {len(changed)}")
    print(f"Unique Chinese strings: {len(unique_targets)}")
    print(f"Output SHA-256: {output_sha256}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
