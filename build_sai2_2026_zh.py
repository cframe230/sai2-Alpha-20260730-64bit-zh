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

REPORT_PATH = (
    SCRIPT_DIR / "translation_report.json"
    if LOCAL_PACKAGE is not None
    else REPO_ROOT / "tools" / "translation_report.json"
)
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
FORCED_BY_SOURCE = {
    # These strings are shared by several resource keys in 2026, so one
    # consistent translation must be used at their common storage address.
    "キャンバス": "画布",
    "フォルダ": "文件夹",
}
MANUAL_BY_KEY_SOURCE = {
    ("Bgmode_White", "白"): "白色",
    ("Bgmode_Black", "黒"): "黑色",
    ("Bgmode_Color", "指定色"): "指定颜色",
    ("Bgmode_TrWhite", "透明(白)"): "透明（白色）",
    ("Bgmode_TrBlack", "透明(黒)"): "透明（黑色）",
    ("Bgmode_TrColor", "透明(指定色)"): "透明（指定颜色）",
    ("Selection_Erase", "選択領域を解除"): "取消选区",
    ("Window_Color", "ウィンドウの配色"): "窗口配色",
    ("SwatchMode_Large", "大"): "大",
    ("SwatchMode_Middle", "中"): "中",
    ("SwatchMode_Small", "小"): "小",
    ("LayTxt_ColBinThres", "しきい値"): "阈值",
    ("BrTxt_Dilution", "水分量"): "水分量",
    ("BrCtl_BshpScattering", "散布"): "散布",
    ("BrTxt_SmudgeColoring", "着色"): "着色",
    ("BrCtl_ScatDensity", "流量"): "流量",
    ("BrCtl_ScatScattering", "散布"): "散布",
    ("BrCtl_ScatAllDir", "全方向散布"): "全方向散布",
    ("BrCtl_ScatRandomOrder", "順序ランダム"): "随机顺序",
    ("BrCtl_ShowOpt", "その他  "): "其他  ",
    ("PpTxt_FillSel", "塗り "): "填充 ",
    ("PpTxt_LineWidth", "線幅"): "线宽",
    ("PpTxt_MarkerStart", "始点の記号"): "起点标记",
    ("PpTxt_MarkerEnd", "終点の記号"): "终点标记",
    ("PpLineClip_Outside", "塗りの外側"): "填充外侧",
    ("PbCtl_BevelOff", "解除"): "解除",
    ("MqTxt_Selop", "操作"): "操作",
    ("MqCtl_TfopLattice", "格子変形"): "网格变形",
    ("MqCtl_TfopMesh", "メッシュ変形"): "网格变形",
    ("MqCtl_KeepInkWidth", "図形の線幅を維持"): "保持图形线宽",
    ("MqTxt_Division", "分割数"): "分割数",
    ("MqTxt_Render", "重複部分"): "重叠部分",
    ("MqCtl_RenderOverwrite", "上書き"): "覆盖",
    ("MqCtl_RenderBlend", "合成"): "合成",
    ("MqCtl_SaveGuide", "ガイド保存"): "保存辅助线",
    ("MqCtl_LoadGuide", "ガイド読込"): "加载辅助线",
    ("LsTxt_Selop", "操作"): "操作",
    ("LsCtl_UntranspRegion", "非透明部分"): "不透明区域",
    ("WnTxt_Selop", "操作"): "操作",
    ("WnCtl_UntranspRegion", "非透明部分"): "不透明区域",
    ("GrTxt_Form", "形状"): "形状",
    ("TxCtl_CharSpc", "字間"): "字距",
    ("TxCtl_CharLift", "上下"): "上下偏移",
    ("TxCtl_CharXscl", "横幅"): "横向缩放",
    ("TxCtl_CharYscl", "縦幅"): "纵向缩放",
    ("TxTxt_RubyAdjust", "ルビ配置"): "注音位置",
    ("TxCtl_ShowWdir", "書字方向設定"): "书写方向设置",
    ("TxTxt_WritingDir", "基本書字方向"): "基本书写方向",
    ("TxTxt_ObliqueType", "斜体の傾き"): "倾斜角度",
    ("Prscurv_Title", "筆圧感度曲線"): "笔压感应曲线",
    ("BlendMode_AddSubtract", "明暗"): "明暗",
    ("BlendMode_Hue", "色相"): "色相",
    ("BasNam_Brshape", "散布"): "散布",
    ("BasNam_Scatter", "散布"): "散布",
    ("LayNam_Ngrid", "用紙グリッド"): "纸张网格",
    ("LayNam_Alpha0", "不透明部分"): "不透明区域",
    ("SymmAttr_Divcnt", "分割"): "分割数",
    ("ToolGrp_Basic", "基本"): "基本",
    ("Tool_Scatter", "散布"): "散布",
    ("Toolini_Scatter", "散布"): "散布",
    ("Tool_InkErs", "修正液"): "线稿橡皮",
    ("Toolini_InkErs", "修正液"): "线稿橡皮",
    ("Toolini_BinInkErs", "修正液"): "线稿橡皮",
    ("ArtToolini_Water", "水彩"): "水彩",
    ("AssetName_Broken", "破損"): "损坏",
    ("ToolGroup_Unorganized", "未整理"): "未整理",
    ("AssetGroup_Unorganized", "【未整理】"): "【未整理】",
    ("Bintone_ShapeDiamond", "菱形"): "菱形",
    ("Bintone_ShapeCross", "十字"): "十字",
    ("SnapMode_Knot", "交点"): "交点",
    ("PpLineCat_Solid", "実線"): "实线",
    ("Word_ToolGroup", "群"): "组",
    ("ErrboxTxt_Subject", "対象"): "对象",
    ("AserrTxt_DatCat", "設定内容"): "设置内容",
    ("LostData_ToolGroupOrder", "グループの順序"): "组顺序",
    ("FileViewer_Path", "場所"): "路径",
    ("FileViewer_TypeFilter", "形式絞り込み"): "类型筛选",
    ("FileViewer_FileType", "保存形式"): "保存格式",
    ("FileViewer_Save", "保存"): "保存",
    ("FvMenu_MoveHere", "ここに移動"): "移动到这里",
    ("RcvItem_HS", "操作"): "操作",
    ("OptEnvDsc_Paths", "ローカルドライブ上のパスを指定してください。格納先の変更は次回SAIを起動させた時から反映され、格納されているデータもその時に移動されます。"): "请指定本地驱动器上的路径。存储位置变更将在下次启动 SAI 时生效，现有数据届时也会移动。",
    ("LayPropTxt_BoldA", "分割線"): "每隔",
    ("LayPropTxt_BoldB", "本置き"): "条网格线",
    ("LayPropTxt_ExBoldA", "太線"): "每隔",
    ("LayPropTxt_ExBoldB", "本置き"): "条粗线",
    ("LayPropTxt_DivCount", "分割数 :"): "分割数：",
    ("AsregTxt_ImgType", "画像抽出 :"): "解析方式：",
    ("AsregTxt_Register", "作成方法 :"): "创建方式：",
    ("AsregCtl_RegReplace", "上書き"): "覆盖",
    ("AsregBtn_Register", "作成"): "创建",
    ("AsregCtl_FomCatBshp", "散布"): "散布",
    ("AsmanTxt_ScatTable1", "散布設定１用"): "用于散布参数 1",
    ("AsmanTxt_ScatTable2", "散布設定２用"): "用于散布参数 2",
    ("AsmanTxt_ScatTable3", "散布設定３用"): "用于散布参数 3",
    ("AutoHinv_5", "5文字"): "5 个字符",
    ("TabFltMode_Ver1", "Ver.1方式"): "Ver.1 方式",
    ("SavImgTxt_SavReso", "保存サイズ"): "保存大小",
    ("SavSai2Txt_Caption", "SAI2形式"): "SAI2 格式",
    ("SavBmpTxt_Caption", "BMP形式"): "BMP 文件",
    ("SavJpgCtl_DsHorz", "水平方向"): "水平",
    ("SavJpgCtl_DsVert", "垂直方向"): "垂直",
    ("Astype_ColorHistory", "色履歴"): "颜色历史",
    ("Color_TitleRefcol", "基準色の指定"): "指定基准色",
    ("HueSatTxt_Hue", "色相 :"): "色相：",
    ("Color_Hue", "色相 :"): "色相：",
    ("Bintone_Lpi", "線数"): "线数",
    ("Bintone_ShpCross", "十字"): "十字",
    # 2026 terminology review and corrections.
    ("Canvas_Colmode", "カラーモード"): "颜色模式",
    ("CvnewTxt_ColorMode", "カラーモード :"): "颜色模式：",
    ("SavImgTxt_ColorMode", "カラーモード:"): "颜色模式：",
    ("Layer_SelectLaymask", "レイヤーマスクの選択・解除"): "选择/取消图层蒙版",
    ("Error_LicenseRevoked", "以下のライセンス証明書は失効したライセンスのものであるため拒否されました。"): "以下许可证书对应的许可证已被吊销，因此将被忽略。",
    ("Error_ScatterColor", "選択された散布ビットマップはカラーモードがグレースケールまたは32bit ARGBではありません。"): "所选散布位图的颜色模式不是灰度或 32 位 ARGB。",
    ("Error_ScatterCount", "１つの散布形状に登録できるビットマップは15個までです。"): "一个散布形状最多可注册 15 个位图。",
    ("Error_ScatterDiffBpp", "選択された散布ビットマップは異なるカラーモードが混在しています。"): "所选散布位图混用了不同的颜色模式。",
    ("PeCtl_DfmPath", "マクロ変形 (shift)"): "整体变形 (shift)",
    ("TxCtl_HorzInVert", "縦中横"): "纵排横排",
    ("TxTxt_AutoHinv", "自動縦中横"): "自动纵排横排",
    ("Tool_InkErs", "修正液"): "修正液",
    ("Toolini_InkErs", "修正液"): "修正液",
    ("Toolini_BinInkErs", "修正液"): "修正液",
    ("MqCtl_TfopLattice", "格子変形"): "格子变形",
    ("MqCtl_TfopMesh", "メッシュ変形"): "网格变形",
    ("Pers_FitVg", "パースグリッドをパース定規の緑赤軸平面に配置する"): "将透视网格置于透视标尺的绿红轴平面",
    ("Pers_FitVb", "パースグリッドをパース定規の青赤軸平面に配置する"): "将透视网格置于透视标尺的蓝红轴平面",
    ("Pers_FitVr", "パースグリッドをパース定規の緑青軸平面に配置する"): "将透视网格置于透视标尺的绿蓝轴平面",
    ("Pers_PixCenter", "対称定規中心をピクセル中心に揃える"): "将对称标尺中心对齐到像素中心",
    ("Pers_PixBoundary", "対称定規中心をピクセル境界に揃える"): "将对称标尺中心对齐到像素边界",
    ("PeCtl_MovCp", "制御点追加・移動 (ctrl)"): "移动/添加锚点 (ctrl)",
    ("PeCtl_ConPath", "パス連結 (shift+ctrl+●→●)"): "连接锚点 (shift+ctrl+●→●)",
    ("PeCtl_PointedRounded", "鋭角点切替 (ctrl+alt+●)"): "切换尖角/圆角 (ctrl+alt+●)",
    ("PeCtl_DupPath", "パス複製移動 (shift+ctrl+／)"): "复制并移动路径 (shift+ctrl+/)",
    ("PpRem_Shapechg", "右クリックで図形の情報を取得することができます。"): "提示：右键单击可拾取形状参数。",
    ("Meshdiv_Title", "格子変形・メッシュ変形の分割数"): "格子变形/网格变形的分割数",
    ("MeshdivTxt_HDiv", "横方向の分割数 :"): "横向分割数：",
    ("MeshdivTxt_VDiv", "縦方向の分割数 :"): "纵向分割数：",
    ("MqCtl_SelopNormal", "選択領域を解除してから指定した領域を新しい選択領域とします。"): "取消原选区，并将指定区域设为新选区。",
    ("LsCtl_SelopNormal", "選択領域を解除してから指定した領域を新しい選択領域とします。"): "取消原选区，并将指定区域设为新选区。",
    ("LsTxt_ColThres", "基準色と色差の許容範囲:"): "与基准色的色差容许范围：",
    ("LsCtl_IgnoreRegion", "選択領域を貫通して領域抽出"): "穿透选区检测区域",
    ("WnCtl_IgnoreRegion", "選択領域を貫通して領域抽出"): "穿透选区检测区域",
    ("LsCtl_IgnoreRegion", "選択領域を貫通して領域検出するかどうかを指定します。"): "指定区域检测是否穿透选区。",
    ("WnCtl_IgnoreRegion", "選択領域を貫通して領域検出するかどうかを指定します。"): "指定区域检测是否穿透选区。",
    ("LsCtl_Dilation", "抽出した領域を膨張させる幅を指定します。"): "指定检测区域的扩张宽度。",
    ("WnCtl_Dilation", "抽出した領域を膨張させる幅を指定します。"): "指定检测区域的扩张宽度。",
    ("TxCtl_RubyInto", "修飾キーなしでルビに移動"): "无需修饰键即可移入注音",
    ("TxCtl_RubyInto", "修飾キーなしでルビにカレットを移動するかどうかを指定します。"): "指定是否可在不按修饰键时用方向键将插入符移入注音文本。",
    ("TxCtl_RubyGap", "常にルビの分の行間を空ける"): "始终为注音保留行间距",
    ("TxCtl_RubyGap", "すべての行で常にルビのための隙間を空けるかどうかを指定します。"): "指定是否始终在每行中为注音保留间距。",
    ("TxCtl_LayoutVertBottom", "縦書きの行の下端を基準点に揃えて配置します。"): "将纵排文本底部对齐。",
    ("TxCtl_LayoutHorzBox", "矩形内に横書きの文章を詰め込んで配置します。"): "在矩形内排列横排文本。",
    ("TxCtl_LayoutVertBox", "矩形内に縦書きの文章を詰め込んで配置します。"): "在矩形内排列纵排文本。",
    ("AssetError_Title", "設定ファイルの読み込みエラー"): "素材设置文件加载错误",
    ("AssetError_Fatal", "設定ファイルの読み込みに失敗しました。"): "无法加载素材设置文件。",
    ("AsregMsg_NoBristleHairs", "毛点が存在しないためブリスルを作成することができません。"): "因不存在毛点，无法创建鬃毛。",
    ("AsregMsg_Existing", "すでに同じ名前の素材があります。上書きしますか？"): "已存在同名素材。是否覆盖？",
    ("AsregMsg_Overwrite", "現在選択している素材を上書きしても宜しいですか？"): "是否覆盖当前选中的素材？",
    ("AspopCtl_New", "新規素材を作成します。"): "创建新素材。",
    ("AspopCtl_Add", "現在のキャンバスの画像を新しい素材として登録します。"): "将当前画布图像注册为新素材。",
    ("AspopCtl_Delete", "選択している素材を削除します。"): "删除当前选中的素材。",
    ("AspopCtl_Config", "[素材・ツール管理]ダイアログを開きます。"): "打开[素材与工具管理]对话框。",
    ("FvMenu_CopyHere", "ここにコピー"): "复制到这里",
    ("SavImgTxt_SavReso", "保存サイズ"): "保存尺寸",
    ("SavImgTxt_NewInfo", "保存サイズ :"): "保存尺寸：",
    ("SavImgTxt_ChgReso", "  保存サイズを変更  "): "  更改保存尺寸  ",
    ("SavImgPrg_Resize", "保存サイズを変更しています ..."): "正在更改保存尺寸...",
    ("SavImgCtl_Agray16", "16bpp 不透明度+グレー (A8:G8)"): "16bpp 不透明度+灰度 (A8:G8)",
    ("SavPngTxt_Caption", "PNG形式"): "PNG 文件",
    ("SavTgaTxt_Caption", "TGA形式"): "TGA 文件",
    ("LayPropTxt_GridNx", "分割線の水平間隔 :"): "网格线水平间隔：",
    ("LayPropTxt_GridNy", "分割線の垂直間隔 :"): "网格线垂直间隔：",
    ("LayPropTxt_BoldCx", "太線の水平間隔 :"): "粗线水平间隔：",
    ("LayPropTxt_BoldCy", "太線の垂直間隔 :"): "粗线垂直间隔：",
    ("LayPropTxt_ExBoldCx", "極太線の水平間隔 :"): "特粗线水平间隔：",
    ("LayPropTxt_ExBoldCy", "極太線の垂直間隔 :"): "特粗线垂直间隔：",
    ("Bintone_ShapeGrain", "砂目"): "砂点",
    ("Bintone_ShpGrain", "砂目"): "砂点",
    ("BrCtl_BshpParamNo", "散布の設定を選択します。"): "选择散布参数。",
    ("BrCtl_ScatShapeNo", "散布の設定を選択します。"): "选择散布参数。",
    ("BrCtl_PrsCurve", "[筆圧感度曲線]パネルの表示をON/OFFします。"): "显示/隐藏[笔压感应曲线]面板。",
    ("BrCtl_Reserv", "ブラシツールの現在の設定を記憶します。"): "记忆画笔工具的当前设置。",
    ("Tool_PathChg", "パス変更"): "更改路径",
    ("Error_InitUsrLocUseNew", "作業復元用データと画像サムネールの格納先のフォルダの場所が変更されましたが、変更先のフォルダを作成することができませんでした。\n変更前の場所にフォルダを作成します。"): "工作恢复数据和图像缩略图的存储位置已更改，但无法在新位置创建文件夹。\n将在原位置创建文件夹。",
    ("Error_AsnamDenyChars", "\" * / : < > ? \\ | ^ は素材名に使用できません。"): "以下字符不能用于素材名称：\" * / : < > ? \\ | ^",
    ("Error_FileExisting", "すでに同じ名前のファイルがあります。上書きしますか？"): "已存在同名文件。是否覆盖？",
    ("Error_FioSai1BetaVer", "正式リリース前のテスト版のSAI Ver.1で作成されたSAI形式ファイルには対応していません。"): "不支持由 SAI Ver.1 测试版创建的 SAI 格式文件。",
    ("Error_FioSwatNewVer", "このユーザーパレットファイルは現在使用している古いバージョンのSAI Ver.2では開くことができません。"): "当前使用的旧版 SAI Ver.2 无法打开此用户色板文件。",
    ("Errdsc_HistoryCreate", "ヒストリを新規作成することができませんでした。"): "无法新建历史记录。",
    ("Errdsc_AddAssetSwat", "ユーザーパレットを作成することができませんでした。"): "无法创建用户色板。",
    ("Errdsc_AddAssetLpap", "レイヤー用紙質感を作成することができませんでした。"): "无法创建图层纸张纹理。",
    ("Errdsc_AddAssetScat", "散布画像を作成することができませんでした。"): "无法创建散布图像。",
    ("Errdsc_LoadAssetLpap", "レイヤー用紙質感を読み込むことができませんでした。"): "无法加载图层纸张纹理。",
    ("Errdsc_LoadAssetBlot", "にじみマップを読み込むことができませんでした。"): "无法加载渗色图。",
    ("Errdsc_LoadAssetBrsl", "ブリスルデータを読み込むことができませんでした。"): "无法加载鬃毛数据。",
    ("Errdsc_LoadAssetScat", "散布画像を読み込むことができませんでした。"): "无法加载散布图像。",
    ("LostData_AssetItem", "素材項目本体"): "素材项目",
    ("Error_VdiskBadSecSize", "[Vdisk] セクタサイズが異常です。"): "[Vdisk] 扇区大小异常。",
    ("Error_VdiskBadSecNo", "[Vdisk] セクタ番号が異常です。"): "[Vdisk] 扇区编号异常。",
    ("Error_TTfontTableLacked", "[TTfont] 必須テーブルが存在しません。"): "[TTfont] 缺少必需的字体表。",
    ("Error_TTfontOutsideTable", "[TTfont] 読み込み範囲がテーブルの外です。"): "[TTfont] 读取范围超出字体表。",
    ("Error_BmpPlanes", "[BMPファイル] プレーン数が不正です。"): "[BMP 文件] 平面数无效。",
    ("Error_BmpBfMask", "[BMPファイル] 成分マスクが不正です。"): "[BMP 文件] 通道掩码无效。",
    ("LsCtl_RefCol", "基準色を指定します。Shift+Ctrl+Alt+左クリックでキャンバスから基準色を拾うこともできます。"): "指定基准色。也可按 Shift+Ctrl+Alt 并左键单击画布来拾取基准色。",
    ("ImportTxt_Anounce", "SAI Ver.2 2019-12-31進捗報告版からプログラムの各種設定の保存先が下記のフォルダに変更されました。また、ブラシ形状やテクスチャ等もこのフォルダに格納するよう変更されました。"): "自 SAI Ver.2 Preview.2019-12-31 起，程序各项设置的保存位置改为以下文件夹，画笔形状、纹理等也改为保存在此文件夹中。",
    ("OptKeyDsc_Shift", "ショートカットキーを押下している間だけ項目を選択または機能を有効にして、ショートカットキーを放すと元に戻す操作についての設定です。一部機能のシフト操作についてはショートカットキー割り当てダイアログで個別に指定することができます。"): "设置临时切换操作：仅在按住快捷键时选择项目或启用功能，松开快捷键后恢复原状。部分功能的临时切换可在快捷键分配对话框中单独设置。",
    ("OptEnvDsc_Performance", "ブラシストロークが遅延するなどSAIの動作の応答性が悪い場合は以下の設定を変更することで改善する場合があります。「CPUコアの割り当て方」の変更はSAIを再起動させるまで有効になりません。"): "如果 SAI 响应迟缓（如笔画延迟），调整以下设置可能有所改善。更改[CPU 核心分配方式]需重启 SAI 后生效。",
    ("OptEnvTxt_CpuAssignment", "CPUコアの割り当て方 : "): "CPU 核心分配方式：",
    ("OptEnvCtl_CpuAssignBetter", "A. 全てのCPUコアを処理速度重視で割り当てる"): "A. 使用全部 CPU 核心，优先处理速度",
    ("OptEnvCtl_CpuAssignReduce", "B. 使用するCPUコアの数を制限して応答性重視で割り当てる"): "B. 限制使用的 CPU 核心数量，优先响应速度",
    ("OptEnvRem_CpuAssignment", "SAIの動作の応答性が悪い場合は B を選択して[使用するCPUコアの数]を１～２コア減らしてみてください。"): "如果 SAI 响应迟缓，请选择 B，并尝试将[使用的 CPU 核心数]减少 1～2 个。",
    ("SavImgCtl_CompSize", "9999.99MB"): "9999.99MB",
    ("AspopCtl_Recall", "散布形状を選択した際に散布の設定をリセットするかどうかを指定します。"): "指定选择散布形状时是否重置散布参数。",
    ("AspopCtl_Reserve", "形状に現在の散布の設定を保存します。設定はツール間で共有されます。"): "将当前散布参数保存到形状数据中。参数在所有工具间共享。",
    ("MqCtl_SelopAdd", "指定した領域を選択領域に追加します。"): "将指定区域添加到当前选区。",
    ("LsCtl_SelopAdd", "指定した領域を選択領域に追加します。"): "将指定区域添加到当前选区。",
    ("WnCtl_SelopAdd", "指定した領域を選択領域に追加します。"): "将指定区域添加到当前选区。",
    ("LsCtl_SimiColRegion", "投げ縄で囲んだ範囲内で基準色と色が近い部分を領域として検出します。"): "在套索范围内检测与基准色相近的封闭区域。",
    ("LsCtl_ColThres", "基準色と似た色であるとみなすARGB値の差の範囲を指定します。"): "指定判定为与基准色相近时允许的 ARGB 值差范围。",
    ("Error_FioSpadSignature", "ファイルの内容がスクラッチパッドではありません。"): "文件内容不是便签簿。",
    ("Error_FioSpadNewVer", "このスクラッチパッドファイルは現在使用している古いバージョンのSAI Ver.2では開くことができません。"): "当前使用的旧版 SAI Ver.2 无法打开此便签簿文件。",
    ("Notice_FobidSpad", "この操作はスクラッチパッドに使用することができません。"): "此操作不能用于便签簿。",
    ("Errdsc_AddAssetSpad", "スクラッチパッドを作成することができませんでした。"): "无法创建便签簿。",
    # Corrections for incomplete strings carried over from the previous build.
    ("Error_ExtractZip", "SAIを構成する下記のファイルやフォルダが存在していません。\n配布パッケージのZipファイルはすべて展開してください。\n"): "缺少构成 SAI 所需的以下文件或文件夹。\n请完整解压发行包中的 ZIP 文件。\n",
    ("Error_CanvasShapeParam", "一部の図形系レイヤーのデータに異常を検出しました。\n異常があったストロークまたは図形はパラメータが訂正され赤色に変更されています。"): "检测到部分线稿或形状图层的数据异常。\n异常笔画或形状的参数已修正，并被标为红色。",
    ("Error_LicenseSysid", "以下のライセンス証明書はこのコンピュータのために取得されたものでないため拒否されました。\n(ライセンス証明書に記載されているシステムIDがSAI Ver.2が生成したシステムIDと一致しません)"): "以下许可证书并非为此计算机签发，因此将被忽略。\n（证书中的系统 ID 与 SAI Ver.2 生成的系统 ID 不一致。）",
    ("Error_HisFileFatal", "ヒストリデータのファイルへの書き出しで回復不可能なエラーが発生しました。\n作業中のデータを保存してSAIを再起動してください。"): "将历史记录数据写入文件时发生不可恢复的错误。\n请保存当前工作并重启 SAI。",
    ("Error_RcvFileFatal", "復元ポイントのファイルへの書き出しで回復不可能なエラーが発生しました。\n作業中のデータを保存してSAIを再起動してください。"): "将恢复点写入文件时发生不可恢复的错误。\n请保存当前工作并重启 SAI。",
    ("Error_FioSai2Broken", "ファイルの内容が破損しています。\n\"Error Tiles(...)\" という名前のレイヤーの赤い四角が直下のレイヤーの破損箇所を示しています。"): "文件内容已损坏。\n名为“Error Tiles(...)”的图层中的红色方块表示其下方图层的损坏位置。",
    ("Notice_EndsesFilter", "画像変形やフィルタの実行中にシャットダウンまたはログオフすることはできません。\n画像変形やフィルタを終了させてからシャットダウンまたはログオフをやり直してください。"): "执行图像变形或滤镜时无法关机或注销。\n请结束图像变形或滤镜后重试。",
    ("Notice_MovDatDir", "作業復元用データと画像サムネールの格納先を下記のフォルダに変更されました。\n格納されているデータの移動を行ってからSAIを起動します。\n※ 格納先の変更は2017-07-29版以前の進捗報告版には適用されません。"): "工作恢复数据和图像缩略图的存储位置已更改为以下文件夹。\n移动现有数据后将启动 SAI。\n※ 此位置变更不适用于 SAI Ver.2 Preview.2017-07-29 及更早版本。",
    ("Toolini_DotPen", "ドット絵\nペン"): "像素画\n笔",
    ("V1Toolini_Acrylic1", "ｷｬﾝﾊﾞｽ\nｱｸﾘﾙ"): "画布\n丙烯",
    ("V1Toolini_Acrylic2", "画用紙\nｱｸﾘﾙ"): "图画纸\n丙烯",
    ("CfmClose_SaveAs", "全ての情報を保存する場合はSAI2形式を選択してください。\nキャンバスを閉じる前に別名で保存しますか？"): "要保存全部信息，请选择 SAI2 格式。\n关闭画布前是否另存为？",
    ("AsmanCfm_DelGroup", "選択したグループを削除しますか？\nグループに格納されていた項目は【未整理】グループに移されます。"): "是否删除选中的组？\n组内项目将移至【未整理】组。",
    ("BrCtl_BshpHQSampling", "OFF ... 縮小時に速度優先で描画します。\nON ... 縮小時に品質優先で描画します。"): "OFF ... 缩小时优先速度。\nON ... 缩小时优先质量。",
    ("BrCtl_ScatAllDir", "OFF ... 画像をストローク方向と直交する方向にのみ散布します。\nON ... 画像を全方向に散布します。"): "OFF ... 仅沿与笔画方向垂直的方向散布图像。\nON ... 向所有方向散布图像。",
    ("BrCtl_ScatGaussDistrib", "OFF ... 画像を一様な密度で散布します。\nON ... 画像をカーソルから離れるほど密度が低くなるように散布します。"): "OFF ... 以均匀密度散布图像。\nON ... 距光标越远，散布密度越低。",
    ("BrCtl_ScatAbsoluteSize", "OFF ... 画像を[ブラシサイズ]と[倍率]に応じた大きさで描画します。\nON ... 画像を[画像のサイズ]に応じた大きさで描画します。"): "OFF ... 按[画笔大小]和[倍率]计算的尺寸绘制图像。\nON ... 按[图像尺寸]绘制图像。",
    ("BrCtl_ScatIntPosition", "OFF ... 画像を与えられた座標にそのまま描画します。\nON ... 画像の中心をピクセル境界に揃えて描画します。"): "OFF ... 按给定坐标直接绘制图像。\nON ... 将图像中心对齐像素边界后绘制。",
    ("BrCtl_ScatHQSampling", "OFF ... 縮小時に速度優先で描画します。\nON ... 縮小時に品質優先で描画します。"): "OFF ... 缩小时优先速度。\nON ... 缩小时优先质量。",
    ("BrCtl_ScatAplEachShape", "OFF ... 色に関するぶれをストローク毎に適用します。\nON ... 色に関するぶれを個々の形状毎に適用します。"): "OFF ... 每个笔画应用一次颜色抖动。\nON ... 对每个形状分别应用颜色抖动。",
    ("Lib_EndsesShutdown", "ダイアログボックスが開かれている間はシャットダウンまたはログオフすることができません。\nダイアログボックスを閉じてからシャットダウンまたはログオフをやり直してください。"): "对话框打开时无法关机或注销。\n请关闭对话框后重试。",
    ("Error_CanvasResZero", "キャンバスの印刷解像度が 1 pixels/inch 以上になっていません。"): "画布打印分辨率未达到 1 像素/英寸。",
    ("Error_CanvasPpiMax", "キャンバスの印刷解像度が上限の 25400 pixels/inch を超えています。"): "画布打印分辨率超过 25400 像素/英寸的上限。",
    ("Error_CanvasPpcMax", "キャンバスの印刷解像度が上限の 10000 pixels/cm を超えています。"): "画布打印分辨率超过 10000 像素/厘米的上限。",
    ("Error_Sai1NoThumb", "No Thumnail"): "无缩略图",
    ("Error_Sai1BetaVer", "Beta Version"): "测试版",
    ("BrCtl_ScatWtoHJitter", "WHぶれ"): "宽高比抖动",
    ("AspopCfm_DelScratchPad", "下記のスクラッチパッドを削除しますか？"): "是否删除以下便签簿？",
    ("BasNam_ScratchPad", "スクラッチパッド"): "便签簿",
    ("Astype_ScratchPad", "スクラッチパッド"): "便签簿",
    ("ColSw_ScratchPad", "スクラッチパッドを表示します。"): "显示便签簿。",
    ("CvmetCtl_OldMetrics", "999999mm × 999999mm (999999 pixels/inch) ----"): "999999mm × 999999mm (999999 像素/英寸) ----",
    ("CvmetCtl_NewMetrics", "999999mm × 999999mm (999999 pixels/inch) ----"): "999999mm × 999999mm (999999 像素/英寸) ----",
    ("SavImgCtl_OrgPrtres", "999999 pixels/inch ----"): "999999 像素/英寸 ----",
    ("SavImgCtl_NewPrtres", "999999 pixels/inch ----"): "999999 像素/英寸 ----",
    # Normalize inherited license-certificate terminology.
    ("Error_LicenseNotFound", "有効なライセンス証明書が設定されていないため機能を制限した状態で起動します。"): "未设置有效的许可证书，SAI 将以功能受限状态启动。",
    ("Error_LicenseSlcid", "* このライセンス証明書に書き込まれているシステムID"): "* 此许可证书中记录的系统 ID",
    ("Error_LicenseSyserr", "以下のライセンス証明書の読み込みでエラーが発生しました。"): "读取以下许可证书时发生错误。",
    ("Error_LicenseBroken", "以下のライセンス証明書は内容が破損しているため拒否されました。"): "以下许可证书因内容损坏而被忽略。",
    ("Sysid_Text", "ユーザーライセンス証明書のダウンロードページの「システムID」欄に入力するIDです。このIDはコンピュータ毎に異なる値になります。"): "请将此 ID 输入用户许可证书下载页面的“系统 ID”栏。每台计算机的 ID 均不相同。",
    # In recovery-related UI, Japanese 作業 means the user's work/session,
    # not an engineering project.
    ("App_Shutdown2", "SAIは期限が切れた作業復元データの削除を行っています。"): "SAI 正在删除过期的工作恢复数据。",
    ("ProgBar_Recover", "作業を復元しています..."): "正在恢复工作...",
    ("RevDetect_Title", "強制終了された作業"): "意外终止的工作",
    ("RevDetect_Text", "強制終了された作業を検出しました。編集作業の復元ダイアログを開きますか？"): "检测到意外终止的工作。是否打开工作恢复对话框？",
    ("RcvItem_Work", "作業"): "工作",
    ("RcvdlgDel_Text", "選択している編集作業の復元データを削除しますか？"): "是否删除所选工作的恢复数据？",
    ("OptHisCtl_KeepHis", "強制終了時などに作業を復元できるよう復元ポイントとヒストリを期限まで保管する"): "为便于在意外终止等情况下恢复工作，将恢复点和历史记录保留至到期。",
    ("OptEnvCap_Paths", "ヒストリおよび作業復元用データ、画像ファイルのサムネールの格納先"): "历史记录、工作恢复数据及图像文件缩略图的存储位置",
    ("OptErr_UsrLocNotLocal", "「環境」ページの「ヒストリおよび作業復元用データ、画像ファイルのサムネールの格納先」がローカルドライブ上のパスではありません。"): "“环境”页面中的“历史记录、工作恢复数据及图像文件缩略图的存储位置”不是本地驱动器路径。",
    ("Error_FnamDenyChars", "\" * / : < > ? \\ | はファイル名に使用できません。"): "文件名中不能使用以下字符：\" * / : < > ? \\ |",
    # Clear inherited duplication and mistranslation errors.
    ("Layer_LockPix", "レイヤーへの描画を禁止"): "禁止在图层上绘制",
    ("LayLock_Pixels", "レイヤーへの描画を禁止します。"): "禁止在图层上绘制。",
    ("CvresoCtl_FixWHPixels", "縦横ピクセル数を固定"): "固定横纵像素数",
    ("Filter_Color", "色調補正"): "色调调整",
    ("OptPrfLyRem_AllowInvisProc", "切り取り、移動、変形、ラスタライズ、色調補正が対象です。"): "适用于剪切、移动、变形、栅格化和色调调整。",
    ("OptPrfBrCtl_V1Fealing", "手ぶれ補正 1～15 でのブラシストロークのイリヌキをVer.1と同じ感触にする"): "使手抖修正设为 1～15 时的画笔起收笔手感与 Ver.1 相同",
    ("AssetError_Recoverd", "設定ファイルの破損を検出しました。バックアップから設定を復元しました。"): "检测到设置文件损坏。已从备份恢复设置。",
    ("LayCtl_PapVal", "選択中のレイヤーの用紙質感の強さを指定します。"): "设置所选图层的纸张质感强度。",
    ("OptHisRem_KeepPeriod", "保管期限を過ぎた復元ポイントとヒストリの削除はSAIの終了時に行われます。0 を指定すると削除は行われません。"): "超过保留期限的恢复点和历史记录将在退出 SAI 时删除。设为 0 时不会删除。",
}


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


def clean_translation(text: str, source: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u200b", "")
    # Match the established vocabulary used by the existing localization.
    replacements = {
        "层级": "图层", "刷子": "画笔", "笔刷": "画笔",
        "行程": "笔画", "中风": "笔画", "帆布": "画布", "图像画布": "画布",
        "文件夹路径": "文件夹", "灰阶": "灰度", "取消选择": "取消选区",
        "选择区域": "选区", "控制点": "锚点", "设定": "设置",
        "复原": "恢复", "履历": "历史记录", "缩图": "缩略图",
        "微软": "Microsoft", "视窗": "窗口", "资料夹": "文件夹",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[ \t]+([，。！？：；、])", r"\1", text)
    text = re.sub(r"([（【])\s+", r"\1", text)
    text = re.sub(r"\s+([）】])", r"\1", text)
    # Preserve terminal line breaks used for concatenated diagnostics.
    if source.endswith("\n") and not text.endswith("\n"):
        text += "\n"
    if not source.endswith("\n"):
        text = text.rstrip("\n")
    return text


def normalize_ui_translation(text: str, record: dict) -> str:
    key = record["key"]
    source = record["value"]
    if (key, source) in MANUAL_BY_KEY_SOURCE:
        return MANUAL_BY_KEY_SOURCE[(key, source)]
    exact = {
        "FuncCat_PanelRuler": "标尺控制等",
        "Brushfom_Bristle3": "平面",
        "Pers_LockVp": "锁定所有消失点",
        "Pers_FitVr": "将透视网格置于绿蓝轴平面",
        "PeCtl_DelCp": "删除锚点/曲线 (alt)",
        "PeCtl_DfmPath": "宏变形 (shift)",
        "PeCtl_DfmAnchor": "切换变形分隔 (shift+alt+●)",
        "PeTxt_DrwHnOpr": "- 重绘(*2)",
        "PeTxt_WidHnOpr": "- 固定角度缩放",
        "TxTxt_CharLgap": "行距",
        "TxCtl_RubyLgapScl": "行距",
        "TxTxt_Style": "样式",
        "TxCtl_HorzInVert": "纵中横",
        "TxTxt_AutoHinv": "自动纵中横",
        "CvsizeTxt_Top": "上",
        "CvsizeTxt_Left": "左",
        "CvsizeTxt_Right": "右",
        "CvsizeTxt_Bottom": "下",
        "OptEnvCtl_PriorHigh": "高",
        "Layer_NewNrm": "新建普通图层",
        "Layer_NewShp": "新建形状图层",
        "Layer_NewPat": "新建图案图层",
        "Layer_NewNgrid": "新建纸张网格",
    }
    if key in exact:
        return exact[key]
    if (key, source) == ("TxCtl_Superscript", "上付"):
        return "上标"
    if (key, source) == ("TxCtl_Subscript", "下付"):
        return "下标"
    if key.startswith("Brush_Szscl"):
        return source
    text = text.replace("统治者", "标尺").replace("尺子", "标尺")
    text = text.replace("绘画颜色", "绘图颜色").replace("油漆颜色", "绘图颜色")
    text = text.replace("控制点", "锚点").replace("线条艺术", "线稿")
    text = text.replace("中风", "笔画").replace("行程", "笔画").replace("笔划", "笔画")
    text = re.sub(r"(?<!图)层(?!级)", "图层", text)
    if "Ruby" in key or "Ruby" in record.get("english", ""):
        text = text.replace("红宝石", "注音").replace("Ruby", "注音").replace("ruby", "注音")
    return text


def compact_to_capacity(text: str, capacity: int) -> str:
    if len(text) <= capacity:
        return text
    substitutions = [
        ("Microsoft", "微软"), ("Windows", "Win"), ("文件夹", "目录"),
        ("无法进行", "无法"), ("无法执行", "不能"), ("无法创建", "不能创建"),
        ("是否要", "是否"), ("请执行", "请"), ("请进行", "请"),
        ("发生了", "发生"), ("已经", "已"), ("当前", "现有"),
        ("的数量", "数"), ("的设置", "设置"), ("的文件", "文件"),
        ("的文件夹", "目录"), ("程序", "软件"), ("像素。", "像素"),
    ]
    for old, new in substitutions:
        text = text.replace(old, new)
        if len(text) <= capacity:
            return text
    # Punctuation is preferable but expendable for a size-constrained resource.
    while len(text) > capacity and text[-1:] in "。.!！?？":
        text = text[:-1]
    return text


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

    image, records, english_records, translation_targets = build_translation_inputs()

    proposals = []
    sources = {"translation.json": len(records)}
    for record, target in zip(records, translation_targets):
        source = record["value"]
        item = {**record, "translation": target, "origin": "translation.json"}
        proposals.append(item)

    changed = [proposal for proposal in proposals if proposal["translation"] != proposal["value"]]
    unique_targets = list(dict.fromkeys(proposal["translation"] for proposal in changed))
    section_strings = unique_targets + ([UI_FONT_NAME] if UI_FONT_NAME not in unique_targets else [])

    report = {
        "source_version": "2026.07.30",
        "source_sha256": EXPECTED_HASHES["2026.07.30 original"],
        "japanese_records": len(records),
        "records_by_translation_source": sources,
        "patched_locale_records": len(changed),
        "unique_chinese_strings": len(unique_targets),
        "translations": [
            {"key": p["key"], "ja": p["value"], "zh_cn": p["translation"], "en": p.get("english", ""), "origin": p["origin"]}
            for p in proposals
        ],
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
        shutil.copy2(NEW_ORIGINAL, OUTPUT / "sai2.original.exe")
    else:
        if OUTPUT.exists():
            shutil.rmtree(OUTPUT)
        shutil.copytree(OFFICIAL_PACKAGE, OUTPUT)
        write_executable(OUTPUT / "sai2.exe", image.data)
        shutil.copy2(NEW_ORIGINAL, OUTPUT / "sai2.original.exe")
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

    report["output_sha256"] = sha256(OUTPUT / "sai2.exe")
    report["pe_checksum"] = f"0x{checksum:08X}"
    report["added_section"] = {"name": ".zhcn", "rva": f"0x{new_section_rva:X}", "bytes": len(string_payload)}
    report["ui_font"] = UI_FONT_NAME
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Built: {OUTPUT}")
    print(f"Patched locale records: {len(changed)}")
    print(f"Unique Chinese strings: {len(unique_targets)}")
    print(f"Output SHA-256: {report['output_sha256']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
