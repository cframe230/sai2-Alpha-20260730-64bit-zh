#!/usr/bin/env python3
"""Automatically adapt and apply the Simplified Chinese SAI2 UI patch.

The patcher discovers locale records and font references from the PE image. It
does not depend on a version hash, fixed file offsets, or record ordering.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import threading
import traceback


APP_NAME = "SAI2简中翻译工具"
UI_FONT_SOURCES = ("Meiryo UI", "MS UI Gothic")
UI_FONT_NAME = "Microsoft YaHei UI"
KEY_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,}\Z")
VERSION_RE = re.compile(r"(?:Alpha|Preview)\.(\d{4}\.\d{2}\.\d{2}[a-z]?)", re.IGNORECASE)
JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

# Keys/texts present in Preview.2026.07.02b but renamed or removed in later
# Alpha builds.  Keeping them here also makes the bundled EXE self-contained.
LEGACY_TRANSLATIONS = [
    ("Error_SaiOldVer", "正式リリース前のテスト版のSAI Ver.1で作成されたSAI形式ファイルにはまだ対応していません。", "尚不支持由 SAI Ver.1 正式发布前测试版创建的 SAI 格式文件。"),
    ("Error_FileCompoCount", "レイヤーの成分数が上限の 5 を超えています。", "图层的通道数超过上限 5。"),
    ("Error_LayerMaxCount", "レイヤー数が上限の 8190 枚を超えました。", "图层数量超过上限 8190。"),
    ("Bgmode_None", "指定しない", "不指定"),
    ("Layer_NewCol", "新規レイヤー(カラー)", "新建图层（彩色）"),
    ("Grid_SelVgFore", "グリッド面を緑軸回りに正順で変更", "绕绿轴依次切换网格面"),
    ("Grid_SelVgInvt", "グリッド面を緑軸回りに逆順で変更", "绕绿轴反向切换网格面"),
    ("Grid_SelVbFore", "グリッド面を青軸回りに正順で変更", "绕蓝轴依次切换网格面"),
    ("Grid_SelVbInvt", "グリッド面を青軸回りに逆順で変更", "绕蓝轴反向切换网格面"),
    ("Grid_MovVgFar", "パースグリッドを緑軸に沿って奥側に移動", "沿绿轴将透视网格向远处移动"),
    ("Grid_MovVgNear", "パースグリッドを緑軸に沿って手前に移動", "沿绿轴将透视网格向近处移动"),
    ("Grid_MovVbFar", "パースグリッドを青軸に沿って奥側に移動", "沿蓝轴将透视网格向远处移动"),
    ("Grid_MovVbNear", "パースグリッドを青軸に沿って手前に移動", "沿蓝轴将透视网格向近处移动"),
    ("Grid_MovVrFar", "パースグリッドを赤軸に沿って奥側に移動", "沿红轴将透视网格向远处移动"),
    ("Grid_MovVrNear", "パースグリッドを赤軸に沿って手前に移動", "沿红轴将透视网格向近处移动"),
    ("WnCtl_TranspArea", "描線で囲まれた透明部分", "线条围住的透明区域"),
    ("WnCtl_SimiColArea", "色差が範囲内の部分", "色差在范围内的区域"),
    ("WnCtl_AllSimiColPix", "色差が範囲内の全ピクセル", "色差在范围内的所有像素"),
    ("TxTxt_Layout", "配置", "布局"),
    ("TxCtl_Vert", "縦書き", "竖排"),
    ("TxTxt_Color", "文字色", "文字颜色"),
    ("TxTxt_Size", "文字サイズ", "文字大小"),
    ("TxTxt_Px", "px", "px"),
    ("TxCtl_Hint", "輪郭をピクセル境界に揃える", "使轮廓对齐像素边界"),
    ("ToolOpt_Title", "ツール動作詳細", "工具行为详细设置"),
    ("LayNam_Mask", "マスク", "蒙版"),
    ("OldDir_Title", "PaintTool SAI Ver.2 - ブラシ形状やテクスチャ類の格納先の変更についての警告", "PaintTool SAI Ver.2 - 画笔形状与纹理存储位置变更警告"),
    ("OldDir_Warning", "SAI Ver.2 2020-01-07進捗報告版からブラシ形状やテクスチャ類の格納先が \"<ドキュメント>\\SYSTEMAX Software Development\\SAIv2\\settings\" に\n変更されたため下記のフォルダは使用されなくなりました。これらのフォルダを削除するとこの警告は表示されなくなります。\n", "自 SAI Ver.2 2020-01-07 进度报告版起，画笔形状与纹理的存储位置已改为 \"<文档>\\SYSTEMAX Software Development\\SAIv2\\settings\"。\n因此不再使用以下文件夹。删除这些文件夹后将不再显示此警告。\n"),
    ("OldDir_Guidance", "自作したブラシ形状やテクスチャ類がある場合は新しい格納先のそれぞれ対応するフォルダに移してから上記のフォルダを削除してください。\n(ブラシ形状の新しい格納先は \"<ドキュメント>\\SYSTEMAX Software Development\\SAIv2\\settings\\brushfom\" になることにご注意ください)", "如果有自制的画笔形状或纹理，请先将其移动到新存储位置中对应的文件夹，再删除上述文件夹。\n（请注意，画笔形状的新存储位置为 \"<文档>\\SYSTEMAX Software Development\\SAIv2\\settings\\brushfom\"）"),
    ("JpegSave_Title", "JPEG保存", "JPEG 保存"),
    ("JpegSaveTxt_Scale", "表示倍率:", "显示倍率："),
    ("JpegSaveTxt_Image", "画像:", "图像："),
    ("JpegSaveCtl_Jpeg", "JPEG画像", "JPEG 图像"),
    ("JpegSaveTxt_Width", "水平ピクセル数 :", "水平像素数："),
    ("JpegSaveCtl_Width", "999999", "999999"),
    ("JpegSaveTxt_Height", "垂直ピクセル数 :", "垂直像素数："),
    ("JpegSaveCtl_Height", "999999", "999999"),
    ("FileViewer_Filter", "絞り込み :", "筛选："),
    ("Asreg_Swatch", "新規ユーザーパレット", "新建用户调色板"),
    ("Asreg_ScratchPad", "新規スクラッチパッド", "新建便签簿"),
    ("Asreg_LayerPaper", "新規レイヤー用紙質感", "新建图层纸张纹理"),
    ("Asreg_BrushForm", "新規ブラシ形状", "新建画笔形状"),
    ("Asreg_Scatter", "新規散布ツール用画像", "新建散布工具图像"),
    ("Asreg_BrushTexture", "新規ブラシテクスチャ", "新建画笔纹理"),
    ("AsregCtl_ImgTypeBKonWH", "白背景上の黒部分", "白色背景上的黑色部分"),
    ("AsregCtl_ImgTypeWHonBK", "黒背景上の白部分", "黑色背景上的白色部分"),
    ("FuncCat_Test", "テスト", "测试"),
    ("Test_DispChange", "画面解像度変更シミュレーション", "屏幕分辨率变更模拟"),
    ("Test_DrawParts", "部品画像作成", "创建部件图像"),
    ("WnCtl_TranspArea", "クリック位置の周囲の描線で囲まれた透明部分を領域とします。", "将单击位置周围由线条围住的透明部分作为区域。"),
    ("WnCtl_SimiColArea", "クリック位置のピクセルの周囲で色が近い部分を領域とします。", "将单击位置像素周围颜色相近的部分作为区域。"),
    ("WnCtl_AllSimiColPix", "クリック位置のピクセルと色が近い全ピクセルを領域とします。", "将与单击位置像素颜色相近的所有像素作为区域。"),
    ("ToolCtl_Reserv", "ツールの現在の設定を記憶します。", "记忆工具的当前设置。"),
    ("ToolCtl_Recall", "記憶しておいたツールの設定を復元します。\nボタンアイコンが赤い間にもう一度を押すと復元を取り消すことができます。", "恢复已记忆的工具设置。\n按钮图标为红色时再次按下，可撤销此次恢复。"),
    ("ToolCtl_Option", "[ツール動作詳細]パネルを表示します。", "显示或隐藏“工具行为详细设置”面板。"),
    ("OptKeyCtl_FsChgCol", "描画色切り替えのショートカットキーのシフト操作を有効にする", "启用绘图颜色切换快捷键的临时切换操作"),
    ("OptKeyCtl_FsEnable", "一部機能のショートカットキーのシフト操作を有効にする", "启用部分功能快捷键的临时切换操作"),
    ("OptKeyRem_FsEnable", "ビューの水平反転、定規無効モード、直線モード が対象です。", "适用于：视图水平翻转、忽略尺子和直线模式。"),
    ("OptPrfNvCap_MaxSize", "分離時の最大サイズ", "分离时的最大尺寸"),
    ("OptPrfNvTxt_MaxWidth", "最大幅 : ", "最大宽度："),
    ("OptPrfNvTxt_MaxHeight", "最大高 : ", "最大高度："),
    ("OptPrfNvTxt_TrueWidth", "実際の最大幅 : ", "实际最大宽度："),
    ("OptPrfNvCtl_TrueWidth", "99999px (999%)", "99999px (999%)"),
    ("OptPrfNvTxt_TrueHeight", "実際の最大高 : ", "实际最大高度："),
    ("OptPrfNvCtl_TrueHeight", "99999px (999%)", "99999px (999%)"),
    ("OptPrfNvRem_MaxSize", "設定可能な値は 512～4096 です。実際のピクセル数は「操作パネルの部品のサイズ」およびモニタのDPIに応じて拡大されます。", "可设置的值为 512～4096。实际像素数会根据“操作面板部件大小”和显示器 DPI 进行缩放。"),
    ("BrCtl_ScatAllDir", "全方向に散布", "向所有方向散布"),
    ("BrCtl_Ver1DensPrs", "筆圧濃度補正を無効化", "禁用笔压浓度校正"),
    ("TxCtl_Bold", "太字", "粗体"),
    ("TxCtl_Italic", "斜体", "斜体"),
]


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", app_dir()))
    bundled = base / name
    return bundled if bundled.exists() else app_dir() / name


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


class PEImage:
    def __init__(self, path: Path):
        self.path = path
        self.data = bytearray(path.read_bytes())
        if self.data[:2] != b"MZ":
            raise ValueError(f"不是有效的 Windows PE 文件：{path}")
        self.pe_offset = struct.unpack_from("<I", self.data, 0x3C)[0]
        if self.data[self.pe_offset:self.pe_offset + 4] != b"PE\0\0":
            raise ValueError(f"PE 签名无效：{path}")
        self.number_of_sections_offset = self.pe_offset + 6
        self.number_of_sections = struct.unpack_from("<H", self.data, self.number_of_sections_offset)[0]
        optional_size = struct.unpack_from("<H", self.data, self.pe_offset + 20)[0]
        self.optional_offset = self.pe_offset + 24
        if struct.unpack_from("<H", self.data, self.optional_offset)[0] != 0x20B:
            raise ValueError("仅支持 64 位 SAI2")
        self.image_base = struct.unpack_from("<Q", self.data, self.optional_offset + 24)[0]
        self.checksum_offset = self.optional_offset + 64
        self.section_table_offset = self.optional_offset + optional_size
        self.sections: list[tuple[str, int, int, int, int]] = []
        self.layout_modified_ranges: list[tuple[int, int]] = []
        for index in range(self.number_of_sections):
            offset = self.section_table_offset + index * 40
            name = bytes(self.data[offset:offset + 8]).rstrip(b"\0").decode("ascii", "replace")
            virtual_size, rva, raw_size, raw_offset = struct.unpack_from("<IIII", self.data, offset + 8)
            self.sections.append((name, rva, virtual_size, raw_offset, raw_size))

    @staticmethod
    def _align(value: int, alignment: int) -> int:
        return (value + alignment - 1) // alignment * alignment

    def has_section(self, name: str) -> bool:
        return any(section[0] == name for section in self.sections)

    def va_to_offset(self, va: int) -> int:
        rva = va - self.image_base
        for _name, section_rva, virtual_size, raw_offset, raw_size in self.sections:
            if section_rva <= rva < section_rva + max(virtual_size, raw_size):
                result = raw_offset + rva - section_rva
                if 0 <= result < len(self.data):
                    return result
        raise ValueError(f"地址 0x{va:X} 不在 PE 映射区内")

    def offset_to_rva(self, offset: int) -> int:
        for _name, section_rva, _virtual_size, raw_offset, raw_size in self.sections:
            if raw_offset <= offset < raw_offset + raw_size:
                return section_rva + offset - raw_offset
        raise ValueError(f"文件偏移 0x{offset:X} 不在 PE 映射区内")

    def utf16(self, va: int, cache: dict[int, str] | None = None, limit: int = 16384) -> str:
        if cache is not None and va in cache:
            return cache[va]
        offset = self.va_to_offset(va)
        end = offset
        while end + 1 < len(self.data) and end - offset < limit:
            if self.data[end:end + 2] == b"\0\0":
                result = bytes(self.data[offset:end]).decode("utf-16le")
                if cache is not None:
                    cache[va] = result
                return result
            end += 2
        raise ValueError(f"UTF-16 字符串未终止：0x{va:X}")

    def locale_record(self, offset: int, cache: dict[int, str]) -> dict | None:
        try:
            ident, key_va, value_va = struct.unpack_from("<QQQ", self.data, offset)
            key = self.utf16(key_va, cache)
            if not KEY_RE.fullmatch(key):
                return None
            return {
                "record_offset": offset,
                "id": ident,
                "key": key,
                "value": self.utf16(value_va, cache),
            }
        except (ValueError, UnicodeError, struct.error):
            return None

    def discover_record_runs(self) -> list[list[dict]]:
        """Discover contiguous arrays of (id, key pointer, value pointer)."""
        cache: dict[int, str] = {}
        valid: dict[int, dict] = {}
        scan_sections = [section for section in self.sections if section[0] in (".rdata", ".data")]
        for _name, _rva, _virtual_size, raw_offset, raw_size in scan_sections:
            for offset in range(self._align(raw_offset, 8), raw_offset + raw_size - 23, 8):
                record = self.locale_record(offset, cache)
                if record is not None:
                    valid[offset] = record
        runs: list[list[dict]] = []
        for offset in sorted(valid):
            if offset - 24 in valid:
                continue
            run = []
            cursor = offset
            while cursor in valid:
                run.append(valid[cursor])
                cursor += 24
            if len(run) >= 3:
                runs.append(run)
        return runs

    def find_utf16_rip_references(self, text: str) -> list[tuple[int, int]]:
        needle = text.encode("utf-16le") + b"\0\0"
        string_offset = self.data.find(needle)
        if string_offset < 0:
            return []
        target_rva = self.offset_to_rva(string_offset)
        matches = []
        text_sections = [section for section in self.sections if section[0] in (".text", ".code")]
        for _name, _rva, _virtual_size, raw_start, raw_size in text_sections:
            for raw_offset in range(raw_start, raw_start + raw_size - 7):
                if bytes(self.data[raw_offset:raw_offset + 3]) not in (b"\x48\x8D\x3D", b"\x48\x8D\x05"):
                    continue
                instruction_rva = self.offset_to_rva(raw_offset)
                displacement = struct.unpack_from("<i", self.data, raw_offset + 3)[0]
                if instruction_rva + 7 + displacement == target_rva:
                    matches.append((raw_offset, instruction_rva))
        return matches

    def create_font_quality_blocks(self) -> list[int]:
        """Locate the conditional LOGFONTW.lfQuality block used by font creation."""
        import_directory = self.optional_offset + 112 + 8
        import_rva, import_size = struct.unpack_from("<II", self.data, import_directory)
        if not import_rva or not import_size:
            return []
        descriptor = self.va_to_offset(self.image_base + import_rva)
        iat_rva = None
        while descriptor + 20 <= len(self.data):
            original_thunk, _time, _forwarder, dll_rva, first_thunk = struct.unpack_from("<IIIII", self.data, descriptor)
            if not any((original_thunk, dll_rva, first_thunk)):
                break
            dll_offset = self.va_to_offset(self.image_base + dll_rva)
            dll_end = self.data.find(b"\0", dll_offset)
            dll_name = bytes(self.data[dll_offset:dll_end]).decode("ascii", "replace").lower()
            if dll_name == "gdi32.dll":
                thunk_rva = original_thunk or first_thunk
                thunk_offset = self.va_to_offset(self.image_base + thunk_rva)
                index = 0
                while True:
                    entry = struct.unpack_from("<Q", self.data, thunk_offset + index * 8)[0]
                    if not entry:
                        break
                    if not entry >> 63:
                        name_offset = self.va_to_offset(self.image_base + entry) + 2
                        name_end = self.data.find(b"\0", name_offset)
                        if bytes(self.data[name_offset:name_end]) == b"CreateFontIndirectW":
                            iat_rva = first_thunk + index * 8
                            break
                    index += 1
            if iat_rva is not None:
                break
            descriptor += 20
        if iat_rva is None:
            return []
        result = []
        quality_block = bytes.fromhex(
            "0F BA E7 0C 73 06 C6 40 22 04 EB 0A "
            "0F BA E7 0D 73 04 C6 40 22 03"
        )
        for name, _rva, _virtual_size, raw_start, raw_size in self.sections:
            if name not in (".text", ".code"):
                continue
            for call_offset in range(raw_start, raw_start + raw_size - 6):
                if self.data[call_offset:call_offset + 2] != b"\xff\x15":
                    continue
                call_rva = self.offset_to_rva(call_offset)
                target_rva = call_rva + 6 + struct.unpack_from("<i", self.data, call_offset + 2)[0]
                if target_rva != iat_rva:
                    continue
                start = max(raw_start, call_offset - 256)
                quality_offset = self.data.find(quality_block, start, call_offset)
                if quality_offset >= 0:
                    result.append(quality_offset)
        return list(dict.fromkeys(result))

    def add_readonly_data_section(self, name: bytes, payload: bytes) -> int:
        file_alignment = struct.unpack_from("<I", self.data, self.optional_offset + 36)[0]
        section_alignment = struct.unpack_from("<I", self.data, self.optional_offset + 32)[0]
        size_of_headers = struct.unpack_from("<I", self.data, self.optional_offset + 60)[0]
        header_offset = self.section_table_offset + self.number_of_sections * 40
        if header_offset + 40 > size_of_headers or any(self.data[header_offset:header_offset + 40]):
            return self.extend_last_section(payload)
        last_end = max(rva + max(virtual_size, raw_size) for _n, rva, virtual_size, _o, raw_size in self.sections)
        new_rva = self._align(last_end, section_alignment)
        new_raw_offset = self._align(len(self.data), file_alignment)
        new_raw_size = self._align(len(payload), file_alignment)
        self.data.extend(b"\0" * (new_raw_offset - len(self.data)))
        self.data.extend(payload)
        self.data.extend(b"\0" * (new_raw_size - len(payload)))
        header = struct.pack(
            "<8sIIIIIIHHI", name.ljust(8, b"\0"), len(payload), new_rva,
            new_raw_size, new_raw_offset, 0, 0, 0, 0, 0x40000040,
        )
        self.data[header_offset:header_offset + 40] = header
        self.number_of_sections += 1
        struct.pack_into("<H", self.data, self.number_of_sections_offset, self.number_of_sections)
        initialized_size = struct.unpack_from("<I", self.data, self.optional_offset + 8)[0]
        struct.pack_into("<I", self.data, self.optional_offset + 8, initialized_size + new_raw_size)
        struct.pack_into("<I", self.data, self.optional_offset + 56, self._align(new_rva + len(payload), section_alignment))
        self.sections.append((name.decode("ascii"), new_rva, len(payload), new_raw_offset, new_raw_size))
        self.layout_modified_ranges = [
            (self.number_of_sections_offset, self.number_of_sections_offset + 2),
            (self.optional_offset + 8, self.optional_offset + 12),
            (self.optional_offset + 56, self.optional_offset + 60),
            (header_offset, header_offset + 40),
        ]
        return new_rva

    def extend_last_section(self, payload: bytes) -> int:
        """Append payload to the last physical section when no header slot remains."""
        index, section = max(enumerate(self.sections), key=lambda item: item[1][3] + item[1][4])
        name, section_rva, virtual_size, raw_offset, raw_size = section
        raw_end = raw_offset + raw_size
        if raw_end != len(self.data):
            raise ValueError("PE 节表已满且文件含附加数据，无法安全扩展")
        file_alignment = struct.unpack_from("<I", self.data, self.optional_offset + 36)[0]
        section_alignment = struct.unpack_from("<I", self.data, self.optional_offset + 32)[0]
        payload_delta = max(raw_size, virtual_size)
        payload_offset = raw_offset + payload_delta
        self.data.extend(b"\0" * (payload_offset - len(self.data)))
        self.data.extend(payload)
        new_raw_size = self._align(payload_delta + len(payload), file_alignment)
        self.data.extend(b"\0" * (raw_offset + new_raw_size - len(self.data)))
        new_virtual_size = payload_delta + len(payload)
        header_offset = self.section_table_offset + index * 40
        struct.pack_into("<I", self.data, header_offset + 8, new_virtual_size)
        struct.pack_into("<I", self.data, header_offset + 16, new_raw_size)
        initialized_size = struct.unpack_from("<I", self.data, self.optional_offset + 8)[0]
        struct.pack_into("<I", self.data, self.optional_offset + 8, initialized_size + new_raw_size - raw_size)
        size_of_image = self._align(section_rva + new_virtual_size, section_alignment)
        struct.pack_into("<I", self.data, self.optional_offset + 56, size_of_image)
        self.sections[index] = (name, section_rva, new_virtual_size, raw_offset, new_raw_size)
        self.layout_modified_ranges = [
            (self.optional_offset + 8, self.optional_offset + 12),
            (self.optional_offset + 56, self.optional_offset + 60),
            (header_offset + 8, header_offset + 12),
            (header_offset + 16, header_offset + 20),
        ]
        return section_rva + payload_delta


def load_translation_memory(path: Path | None = None) -> tuple[dict[str, list[dict]], dict]:
    source = path or resource_path("translation.json")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"无法读取翻译库：{source}") from exc
    items = data.get("translations") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError("translation.json 缺少 translations 数组")
    memory: dict[str, list[dict]] = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("key"), str) and isinstance(item.get("zh_cn"), str):
            memory.setdefault(item["key"], []).append(item)
    for key, ja, zh_cn in LEGACY_TRANSLATIONS:
        candidates = memory.setdefault(key, [])
        if not any(item.get("ja") == ja for item in candidates):
            candidates.append({"key": key, "ja": ja, "zh_cn": zh_cn, "origin": "legacy-20260702b"})
    if not memory:
        raise ValueError("翻译库为空")
    return memory, data


def choose_translation(record: dict, memory: dict[str, list[dict]]) -> tuple[dict | None, str]:
    candidates = memory.get(record["key"], [])
    exact = [item for item in candidates if item.get("ja") == record["value"]]
    if exact:
        return exact[0], "exact"
    if record["key"] == "App_Title":
        return (candidates[0], "version_title") if candidates else (None, "new")
    # Renamed keys are common between Preview and Alpha builds.  Reuse a
    # translation only when the Japanese source text identifies one target
    # unambiguously across the complete memory.
    text_matches = [
        item for items in memory.values() for item in items
        if item.get("ja") == record["value"] and item.get("zh_cn")
    ]
    text_targets = {item["zh_cn"] for item in text_matches}
    if text_matches and len(text_targets) == 1:
        return text_matches[0], "text_match"
    if not candidates:
        return None, "new"
    translations = {item.get("zh_cn") for item in candidates if item.get("zh_cn")}
    if len(candidates) == 1 or len(translations) == 1:
        return candidates[0], "source_changed"
    return None, "ambiguous"


def select_japanese_records(image: PEImage, memory: dict[str, list[dict]]) -> tuple[list[dict], list[dict]]:
    selected_runs = []
    diagnostics = []
    for run in image.discover_record_runs():
        known = [record for record in run if record["key"] in memory]
        ja_exact = sum(any(item.get("ja") == r["value"] for item in memory[r["key"]]) for r in known)
        en_exact = sum(any(item.get("en") == r["value"] for item in memory[r["key"]]) for r in known)
        japanese_values = sum(bool(JAPANESE_RE.search(r["value"])) for r in run)
        known_density = len(known) / len(run)
        is_japanese = (
            len(known) >= 3 and known_density >= 0.25 and ja_exact > en_exact
        ) or (
            japanese_values >= max(2, len(run) // 4) and (known_density >= 0.1 or len(known) == 0)
        )
        diagnostics.append({
            "offset": f"0x{run[0]['record_offset']:X}", "records": len(run),
            "known": len(known), "ja_exact": ja_exact, "en_exact": en_exact,
            "japanese_values": japanese_values, "selected": is_japanese,
        })
        if is_japanese:
            selected_runs.append(run)
    records_by_offset = {
        record["record_offset"]: record for run in selected_runs for record in run
    }
    records = [records_by_offset[offset] for offset in sorted(records_by_offset)]
    if len(records) < 100:
        raise ValueError(f"自动识别到的日文词条过少（{len(records)} 条），已停止以保护 EXE")
    return records, diagnostics


def version_from_records(records: list[dict]) -> str:
    title = next((record["value"] for record in records if record["key"] == "App_Title"), "")
    match = VERSION_RE.search(title)
    return match.group(1) if match else "unknown"


def analyze(source: Path, translation_path: Path | None = None) -> dict:
    image = PEImage(source)
    if image.has_section(".zhcn"):
        raise ValueError("该 EXE 已经汉化，请选择原版 EXE 或原版备份")
    memory, metadata = load_translation_memory(translation_path)
    records, runs = select_japanese_records(image, memory)
    record_keys = {record["key"] for record in records}
    changed_source = []
    new_records = []
    ambiguous_records = []
    text_matched_records = []
    translated = 0
    for record in records:
        item, match_type = choose_translation(record, memory)
        if match_type == "new":
            new_records.append({"key": record["key"], "ja": record["value"]})
            continue
        if match_type == "ambiguous":
            ambiguous_records.append({"key": record["key"], "ja": record["value"]})
            continue
        translated += 1
        if match_type == "text_match":
            text_matched_records.append({"key": record["key"], "ja": record["value"]})
        if match_type == "source_changed" and item is not None:
            changed_source.append({
                "key": record["key"], "old_ja": item.get("ja", ""),
                "new_ja": record["value"], "current_zh_cn": item.get("zh_cn", ""),
            })
    return {
        "source": str(source), "source_sha256": sha256(source),
        "version": version_from_records(records), "records": records,
        "record_count": len(records), "translated_count": translated,
        "new_records": new_records, "changed_source": changed_source,
        "ambiguous_records": ambiguous_records,
        "text_matched_records": text_matched_records,
        "missing_old_keys": sorted(set(memory) - record_keys),
        "runs": runs, "translation_version": metadata.get("source_version", "unknown"),
    }


def calculate_pe_checksum(data: bytearray, checksum_offset: int) -> int:
    temp = bytearray(data)
    temp[checksum_offset:checksum_offset + 4] = b"\0\0\0\0"
    total = 0
    for offset in range(0, len(temp) - 1, 2):
        total += temp[offset] | (temp[offset + 1] << 8)
        total = (total & 0xFFFF) + (total >> 16)
    if len(temp) & 1:
        total += temp[-1]
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + len(temp)) & 0xFFFFFFFF


def build_patch(
    source: Path, output: Path, report_path: Path,
    translation_path: Path | None = None, ui_font: str = "Microsoft YaHei UI",
    clear_type: bool = True,
) -> dict:
    result = analyze(source, translation_path)
    memory, _metadata = load_translation_memory(translation_path)
    image = PEImage(source)
    original_data = bytes(image.data)
    original_length = len(original_data)
    proposals = []
    for record in result["records"]:
        item, _match_type = choose_translation(record, memory)
        if item is None:
            continue
        target = record["value"] if record["key"] == "App_Title" else item.get("zh_cn")
        if isinstance(target, str) and target and target != record["value"]:
            proposals.append((record, target))
    unique_targets = list(dict.fromkeys(target for _record, target in proposals))
    section_strings = unique_targets + ([ui_font] if ui_font not in unique_targets else [])
    payload = bytearray()
    string_offsets = {}
    for text in section_strings:
        string_offsets[text] = len(payload)
        payload.extend(text.encode("utf-16le") + b"\0\0")
    font_references = [
        reference for font in UI_FONT_SOURCES for reference in image.find_utf16_rip_references(font)
    ]
    new_section_rva = image.add_readonly_data_section(b".zhcn", bytes(payload))
    allowed_ranges = list(image.layout_modified_ranges)
    for record, target in proposals:
        pointer_offset = record["record_offset"] + 16
        target_va = image.image_base + new_section_rva + string_offsets[target]
        struct.pack_into("<Q", image.data, pointer_offset, target_va)
        allowed_ranges.append((pointer_offset, pointer_offset + 8))
    font_va = image.image_base + new_section_rva + string_offsets[ui_font]
    for raw_offset, instruction_rva in font_references:
        displacement = font_va - (image.image_base + instruction_rva + 7)
        struct.pack_into("<i", image.data, raw_offset + 3, displacement)
        allowed_ranges.append((raw_offset + 3, raw_offset + 7))
    quality_blocks = image.create_font_quality_blocks() if clear_type else []
    conditional_quality_size = 22
    force_cleartype = b"\xc6\x40\x22\x05" + b"\x90" * (conditional_quality_size - 4)
    for quality_offset in quality_blocks:
        image.data[quality_offset:quality_offset + conditional_quality_size] = force_cleartype
        allowed_ranges.append((quality_offset, quality_offset + conditional_quality_size))
    struct.pack_into("<I", image.data, image.checksum_offset, 0)
    checksum = calculate_pe_checksum(image.data, image.checksum_offset)
    struct.pack_into("<I", image.data, image.checksum_offset, checksum)
    allowed_ranges.append((image.checksum_offset, image.checksum_offset + 4))
    for index, (before, after) in enumerate(zip(original_data, image.data[:original_length])):
        if before != after and not any(start <= index < end for start, end in allowed_ranges):
            raise AssertionError(f"检测到非预期修改：文件偏移 0x{index:X}")
    try:
        output.write_bytes(image.data)
    except PermissionError as exc:
        raise RuntimeError("无法写入 sai2.exe，请先完全退出 SAI2") from exc
    report = {key: value for key, value in result.items() if key != "records"}
    report.update({
        "output": str(output), "output_sha256": sha256(output),
        "patched_records": len(proposals), "unique_chinese_strings": len(unique_targets),
        "font_references_patched": len(font_references), "ui_font": ui_font,
        "clear_type_enabled": clear_type,
        "font_quality_blocks_patched": len(quality_blocks),
    })
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def find_source(folder: Path) -> tuple[Path, Path]:
    live = folder / "sai2.exe"
    backup = folder / "sai2.exe.original.bak"
    if backup.exists():
        return backup, live
    legacy = sorted(folder.glob("sai2.exe.*.bak"))
    if legacy:
        return legacy[0], live
    if live.exists():
        return live, live
    raise FileNotFoundError(f"所选文件夹中没有 sai2.exe：{folder}")


def patch_folder(
    folder: Path, log=lambda _message: None, ui_font: str = "Microsoft YaHei UI",
    clear_type: bool = True,
) -> dict:
    source, output = find_source(folder)
    log(f"分析原版：{source.name}")
    result = analyze(source)
    log(f"识别版本：{result['version']}，日文词条：{result['record_count']}")
    log(f"可翻译：{result['translated_count']}（跨版本匹配 {len(result['text_matched_records'])}），新增：{len(result['new_records'])}，原文变化：{len(result['changed_source'])}，歧义：{len(result['ambiguous_records'])}")
    backup = folder / "sai2.exe.original.bak"
    if not backup.exists():
        shutil.copy2(source, backup)
        source = backup
        log(f"已创建原版备份：{backup.name}")
    report_path = folder / "sai2_zh_adaptation_report.json"
    report = build_patch(source, output, report_path, ui_font=ui_font, clear_type=clear_type)
    ini_path = folder / "sai2.ini"
    if ini_path.exists():
        raw = ini_path.read_bytes()
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        ini = raw.decode(encoding)
        ini = re.sub(r"(?m)^lang\s*=\s*(?:en|ja)\s*$", "lang = ja", ini, count=1)
        ini_path.write_text(ini, encoding=encoding, newline="\r\n")
    log(f"汉化完成：{report['patched_records']} 条，报告：{report_path.name}")
    return report


def restore_folder(folder: Path) -> None:
    backup = folder / "sai2.exe.original.bak"
    if not backup.exists():
        raise FileNotFoundError("没有找到 sai2.exe.original.bak")
    shutil.copy2(backup, folder / "sai2.exe")


def run_gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title(APP_NAME)
    root.geometry("720x500")
    root.minsize(620, 420)
    try:
        root.tk.call("tk", "scaling", 1.25)
    except tk.TclError:
        pass
    folder_var = tk.StringVar(value=str(app_dir()))
    status_var = tk.StringVar(value="请选择SAI2的文件夹")

    frame = ttk.Frame(root, padding=18)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text=APP_NAME, font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
    row = ttk.Frame(frame)
    row.pack(fill="x", pady=(14, 0))
    entry = ttk.Entry(row, textvariable=folder_var)
    entry.pack(side="left", fill="x", expand=True)

    def choose_folder():
        selected = filedialog.askdirectory(initialdir=folder_var.get() or str(app_dir()))
        if selected:
            folder_var.set(selected)

    ttk.Button(row, text="浏览…", command=choose_folder).pack(side="left", padx=(8, 0))
    ttk.Label(frame, text="界面字体：微软雅黑 UI", foreground="#555555").pack(anchor="w", pady=(10, 0))
    log_box = tk.Text(frame, height=15, wrap="word", state="disabled", font=("Consolas", 10))
    log_box.pack(fill="both", expand=True, pady=14)

    def log(message: str):
        def append():
            log_box.configure(state="normal")
            log_box.insert("end", message + "\n")
            log_box.see("end")
            log_box.configure(state="disabled")
            status_var.set(message)
        root.after(0, append)

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x")

    def background(action):
        for button in action_buttons:
            button.configure(state="disabled")
        def worker():
            try:
                action(Path(folder_var.get()).resolve())
            except Exception as exc:
                log(f"错误：{exc}")
                root.after(0, lambda: messagebox.showerror(APP_NAME, str(exc)))
            finally:
                root.after(0, lambda: [button.configure(state="normal") for button in action_buttons])
        threading.Thread(target=worker, daemon=True).start()

    def do_analyze(folder: Path):
        source, _output = find_source(folder)
        result = analyze(source)
        log(f"版本 {result['version']}；识别 {result['record_count']} 条；可翻译 {result['translated_count']} 条")
        log(f"跨版本匹配 {len(result['text_matched_records'])} 条；新增 {len(result['new_records'])} 条；原文变化 {len(result['changed_source'])} 条；歧义 {len(result['ambiguous_records'])} 条")

    def do_patch(folder: Path):
        log(f"界面字体：{UI_FONT_NAME}（ClearType）")
        report = patch_folder(folder, log, UI_FONT_NAME, True)
        root.after(0, lambda: messagebox.showinfo(APP_NAME, f"汉化完成！\n已替换 {report['patched_records']} 条界面文字。"))

    def do_restore(folder: Path):
        restore_folder(folder)
        log("已从原版备份恢复 sai2.exe")
        root.after(0, lambda: messagebox.showinfo(APP_NAME, "恢复完成"))

    action_buttons = [
        ttk.Button(buttons, text="检测版本", command=lambda: background(do_analyze)),
        ttk.Button(buttons, text="开始汉化", command=lambda: background(do_patch)),
        ttk.Button(buttons, text="恢复原版", command=lambda: background(do_restore)),
    ]
    for button in action_buttons:
        button.pack(side="left", padx=(0, 8))
    ttk.Label(buttons, textvariable=status_var).pack(side="right")
    root.mainloop()
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("folder", nargs="?", type=Path, help="包含 sai2.exe 的目录")
    parser.add_argument("--analyze", action="store_true", help="只分析，不修改")
    parser.add_argument("--no-gui", action="store_true", help="使用命令行模式")
    parser.add_argument("--ui-smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.ui_smoke_test:
        import tkinter as tk
        test_root = tk.Tk()
        test_root.withdraw()
        test_root.update()
        test_root.destroy()
        return 0
    if not args.folder and not args.no_gui:
        return run_gui()
    folder = (args.folder or app_dir()).resolve()
    if args.analyze:
        source, _output = find_source(folder)
        result = analyze(source)
        printable = {key: value for key, value in result.items() if key != "records"}
        print(json.dumps(printable, ensure_ascii=False, indent=2))
    else:
        patch_folder(folder, print, UI_FONT_NAME, True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if getattr(sys, "frozen", False):
            traceback.print_exc()
        raise
