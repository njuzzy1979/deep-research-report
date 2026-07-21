"""图三元组动态解析：ImageToken → FigureIR（C-05b）。

将文本阶段产出的 ImageToken 列表，通过 alt 正则捕获图号+题注、路径多候选解析、
PNG IHDR 像素读取、分辨率警告，装配为 FigureIR 列表。

设计依据：02-algorithms.md §A（图三元组解析、路径候选、SVG 协商、像素读取、
强制宽度与分辨率警告）。
"""
from __future__ import annotations

import os
import re
import struct
import urllib.parse

from ..config import (
    FIGURE_LOW_RES_PX_W_THRESHOLD,
    FIGURE_MAX_HEIGHT_CM,
    FIGURE_MAX_WIDTH_CM_DEFAULT,
    FIGURE_MED_RES_PX_W_THRESHOLD,
    RE_FIG_ALT,
)
from ..iotools import read_bytes
from ..ir import FigureIR
from ..issues import Issue, IssueCollector, Level
from ..textstage.tokens import ImageToken

# ---------------------------------------------------------------------------
# 编译正则（来自 config.py 的单一事实来源）
# ---------------------------------------------------------------------------

_RE_FIG_ALT = re.compile(RE_FIG_ALT)

# 图嵌入宽度/高度上限（A4 版心高约 24.6cm，留题注与段距余量）
_IMG_MAX_W_CM = FIGURE_MAX_WIDTH_CM_DEFAULT  # 14.0
_IMG_MAX_H_CM = FIGURE_MAX_HEIGHT_CM         # 20.0

# ---------------------------------------------------------------------------
# 步骤2：路径解析（02 §A.4）
# ---------------------------------------------------------------------------


def _resolve_image_path(
    raw_path: str,
    md_dir: str,
    cli_figures_dir: str | None,
) -> tuple[str | None, bool]:
    """对单张图片的原始路径执行多候选回退解析。

    候选顺序（02 §A.4）：
        1. 若为绝对路径，直接加入候选
        2. 以 md 文件所在目录为基准拼接
        3. 若给出了 CLI --figures-dir，按文件名在该目录查找
        4. 对候选 2/3 追加 URL 解码变体

    对每个候选路径检测 os.path.isfile：
        - 命中 .svg → 同名 .png 协商（02 §A.4 SVG 协商）
        - 命中其他 → 直接返回
        - 全候选失败 → 返回 (None, False)

    Args:
        raw_path: md 中的原始路径（可能含 URL 编码）。
        md_dir: md 文件所在目录的绝对路径。
        cli_figures_dir: CLI --figures-dir 追加候选目录；为 None 时跳过。

    Returns:
        (resolved_path | None, svg_negotiated: bool)
    """
    candidates: list[str] = []

    # 1. 绝对路径
    if os.path.isabs(raw_path):
        candidates.append(raw_path)

    # 2. md 文件目录基准
    candidates.append(os.path.normpath(os.path.join(md_dir, raw_path)))

    # 3. CLI 追加候选（仅按文件名查找）
    if cli_figures_dir:
        candidates.append(
            os.path.normpath(os.path.join(cli_figures_dir, os.path.basename(raw_path)))
        )

    # 4. URL 解码变体（对已加入的候选各追加一次）
    extra: list[str] = []
    for c in candidates:
        try:
            decoded = urllib.parse.unquote(c)
            if decoded != c:
                extra.append(decoded)
        except Exception:
            pass
    candidates.extend(extra)

    # 候选文件存在性检测
    for p in candidates:
        if os.path.isfile(p):
            # SVG → PNG 协商（02 §A.4）
            if p.lower().endswith(".svg"):
                png = os.path.splitext(p)[0] + ".png"
                if os.path.isfile(png):
                    return (png, True)
                else:
                    return (p, False)  # SVG 存在但无同名 PNG → E-IMG-02
            return (p, False)

    return (None, False)  # 全候选失败 → E-IMG-01


# ---------------------------------------------------------------------------
# 步骤3：PNG IHDR 像素读取（R13/R17，02 §A.5）
# ---------------------------------------------------------------------------


def _read_png_pixel_size(path: str) -> tuple[int | None, int | None]:
    """读取 PNG IHDR 头的像素宽高。

    经 iotools.read_bytes(path, limit=33) 读取前 33 字节（R17 裁决：IHDR 读取
    必须经 iotools 完成，G-01 不放松）。若文件不可读或非 PNG 则返回 (None, None)。

    Args:
        path: PNG 文件的绝对路径。

    Returns:
        (px_w, px_h)，解析失败时各为 None。
    """
    try:
        data = read_bytes(path, 33)
    except (FileNotFoundError, OSError):
        return (None, None)

    # PNG 签名校验（8 字节魔数）
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return (None, None)

    # IHDR chunk 布局（02 §A.5）：
    #   offset  8: chunk length（4B，大端）
    #   offset 12: chunk type "IHDR"（4B）
    #   offset 16: width（4B，大端）
    #   offset 20: height（4B，大端）
    px_w = struct.unpack_from(">I", data, 16)[0]
    px_h = struct.unpack_from(">I", data, 20)[0]
    return (px_w, px_h)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def resolve_figures(
    image_tokens: list[ImageToken],
    md_dir: str,
    cli_figures_dir: str | None,
    issues: IssueCollector,
) -> list[FigureIR]:
    """从 ImageToken 列表装配 FigureIR 列表（D1 核心，02 §A）。

    对每个 ImageToken 执行五步流水线：
        1. alt 正则捕获图号+题注（_RE_FIG_ALT）
        2. 路径多候选解析（_resolve_image_path）
        3. PNG IHDR 像素读取（_read_png_pixel_size）
        4. 分辨率警告判定（W-IMG-02 / I-IMG-03）
        5. FigureIR 装配

    Args:
        image_tokens: parse 阶段产出的全部 ImageToken。
        md_dir: md 文件所在目录（用于路径解析基准）。
        cli_figures_dir: CLI --figures-dir 追加候选目录；为 None 时跳过。
        issues: IssueCollector 实例。

    Returns:
        按文档序排列的 FigureIR 列表。
    """
    results: list[FigureIR] = []

    for token in image_tokens:
        alt_raw = token.alt_raw
        path_raw = token.path_raw
        source_line = token.source_line

        # ---- 步骤1：alt 解析 → 图号+题注（02 §A.3） ----
        m = _RE_FIG_ALT.match(alt_raw)
        if m:
            chapter_no = int(m.group(1))
            seq_no = int(m.group(2))
            caption_text = m.group(3)
            figure_id = f"{chapter_no}-{seq_no}"
        else:
            # 不匹配"图X-Y"模式 → W-IMG-01，按无题注普通图处理
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-IMG-01",
                    stage="assemble",
                    message=(
                        f"图片 alt 不匹配「图X-Y」模式，按无题注普通图处理："
                        f"{alt_raw!r}"
                    ),
                    source_line=source_line,
                    element_ref=f"img:{alt_raw[:40]}",
                    suggestion="建议将图片 alt 改为「图X-Y 题注文字」格式",
                )
            )
            chapter_no = 0
            seq_no = 0
            figure_id = f"fig_{source_line}"
            caption_text = alt_raw  # 原样做题注

        bookmark_name = figure_id.replace("-", "_")
        if not bookmark_name.startswith("fig_"):
            bookmark_name = f"fig_{bookmark_name}"

        # ---- 步骤2：路径解析（02 §A.4） ----
        # 网络 URL → 标记返回（产 W-IMG-08）
        if path_raw.startswith(("http://", "https://")):
            issues.append(
                Issue(
                    level=Level.WARNING,
                    code="W-IMG-08",
                    stage="assemble",
                    message=f"网络图片 URL 不嵌入文档，文字占位：{path_raw!r}",
                    source_line=source_line,
                    element_ref=f"img:{figure_id}",
                    suggestion="请将图片下载到本地后引用本地路径",
                )
            )
            results.append(
                FigureIR(
                    figure_id=figure_id,
                    chapter_no=chapter_no,
                    seq_no=seq_no,
                    caption_text=caption_text,
                    alt_raw=alt_raw,
                    path_raw=path_raw,
                    path_resolved=path_raw,  # 网络 URL 原样保留
                    file_exists=False,
                    bookmark_name=bookmark_name,
                    px_w=None,
                    px_h=None,
                    source_line=source_line,
                )
            )
            continue

        resolved_path, svg_negotiated = _resolve_image_path(
            path_raw, md_dir, cli_figures_dir
        )

        if resolved_path is None:
            # 全候选失败 → E-IMG-01
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="E-IMG-01",
                    stage="assemble",
                    message=(
                        f"图片文件不存在（全部回退路径失败）：原始路径 "
                        f"{path_raw!r}，md_dir={md_dir!r}"
                    ),
                    source_line=source_line,
                    element_ref=f"img:{figure_id}",
                    suggestion="请检查图片路径是否正确，或使用 --figures-dir 指定图片目录",
                )
            )
            results.append(
                FigureIR(
                    figure_id=figure_id,
                    chapter_no=chapter_no,
                    seq_no=seq_no,
                    caption_text=caption_text,
                    alt_raw=alt_raw,
                    path_raw=path_raw,
                    path_resolved=path_raw,
                    file_exists=False,
                    bookmark_name=bookmark_name,
                    px_w=None,
                    px_h=None,
                    source_line=source_line,
                )
            )
            continue

        file_exists = True

        # SVG 协商：引用 .svg 存在同名 .png → INFO
        if svg_negotiated:
            issues.append(
                Issue(
                    level=Level.INFO,
                    code="I-CLN-05",
                    stage="assemble",
                    message=(
                        f"SVG→PNG 协商：{path_raw!r} 存在同名 .png，"
                        f"已自动替换为 {resolved_path!r}"
                    ),
                    source_line=source_line,
                    element_ref=f"img:{figure_id}",
                )
            )
        elif path_raw.lower().endswith(".svg"):
            # SVG 存在但无同名 PNG → E-IMG-02
            issues.append(
                Issue(
                    level=Level.ERROR,
                    code="E-IMG-02",
                    stage="assemble",
                    message=(
                        f"引用 SVG 且无同名 PNG 可替代：{path_raw!r}，"
                        f"已定位到 {resolved_path!r}"
                    ),
                    source_line=source_line,
                    element_ref=f"img:{figure_id}",
                    suggestion="请将 SVG 转换为 PNG 格式，或提供同名 PNG 文件",
                )
            )

        # ---- 步骤3：PNG IHDR 像素读取 ----
        px_w: int | None = None
        px_h: int | None = None
        if resolved_path.lower().endswith(".png"):
            px_w, px_h = _read_png_pixel_size(resolved_path)

        # ---- 步骤4：分辨率警告（仅对成功读取像素的 PNG） ----
        if px_w is not None and px_h is not None:
            if px_w < FIGURE_LOW_RES_PX_W_THRESHOLD:
                # <1102px → 14cm 下不足 200dpi，印刷模糊风险
                dpi_est = round(px_w / (_IMG_MAX_W_CM / 2.54))
                issues.append(
                    Issue(
                        level=Level.WARNING,
                        code="W-IMG-02",
                        stage="assemble",
                        message=(
                            f"图片像素宽 {px_w}px（约 {dpi_est}dpi），"
                            f"14cm 下不足 200dpi，印刷存在模糊风险"
                        ),
                        source_line=source_line,
                        element_ref=f"img:{figure_id}",
                        suggestion="建议使用宽度 >= 1102px 的图片（14cm@200dpi）",
                    )
                )
            elif px_w < FIGURE_MED_RES_PX_W_THRESHOLD:
                # [1102, 1654) → 不足 300dpi，可接受
                dpi_est = round(px_w / (_IMG_MAX_W_CM / 2.54))
                issues.append(
                    Issue(
                        level=Level.INFO,
                        code="I-IMG-03",
                        stage="assemble",
                        message=(
                            f"图片像素宽 {px_w}px（约 {dpi_est}dpi），"
                            f"不足 300dpi，可接受"
                        ),
                        source_line=source_line,
                        element_ref=f"img:{figure_id}",
                    )
                )

        # ---- 步骤5：FigureIR 装配 ----
        results.append(
            FigureIR(
                figure_id=figure_id,
                chapter_no=chapter_no,
                seq_no=seq_no,
                caption_text=caption_text,
                alt_raw=alt_raw,
                path_raw=path_raw,
                path_resolved=resolved_path,
                file_exists=file_exists,
                bookmark_name=bookmark_name,
                px_w=px_w,
                px_h=px_h,
                source_line=source_line,
            )
        )

    return results


# ---------------------------------------------------------------------------
# 自检（验收标准）
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # 测试 fixtures 目录（相对于项目根目录）
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]
    _FIXTURES_DIR = _PROJECT_ROOT / "tests" / "fixtures" / "alt-sample"
    _FIGURES_DIR = _FIXTURES_DIR / "figures"

    passed = 0
    failed = 0

    def check(desc: str, condition: bool, detail: str = "") -> None:
        global passed, failed
        if condition:
            passed += 1
            print(f"  [PASS] {desc}")
        else:
            failed += 1
            print(f"  [FAIL] {desc}  -- {detail}")
            if detail:
                print(f"         详情: {detail}")

    # --- 测试1：alt "图1-1 城际动车组产品谱系图" → figure_id="1-1" ---
    print("\n=== 测试1：alt 解析 ===")
    c1 = IssueCollector()
    tokens1 = [
        ImageToken(
            alt_raw="图1-1 城际动车组产品谱系图",
            path_raw="figures/1-1-城际动车组谱系.png",
            source_line=29,
        )
    ]
    r1 = resolve_figures(
        tokens1, str(_FIXTURES_DIR), str(_FIGURES_DIR), c1
    )
    check("返回 1 个 FigureIR", len(r1) == 1, f"实际 {len(r1)}")
    if r1:
        check("figure_id='1-1'", r1[0].figure_id == "1-1", r1[0].figure_id)
        check("chapter_no=1", r1[0].chapter_no == 1, str(r1[0].chapter_no))
        check("seq_no=1", r1[0].seq_no == 1, str(r1[0].seq_no))
        check(
            "caption_text='城际动车组产品谱系图'",
            r1[0].caption_text == "城际动车组产品谱系图",
            r1[0].caption_text,
        )
        check("file_exists=True", r1[0].file_exists, str(r1[0].file_exists))
        check("bookmark_name='fig_1_1'", r1[0].bookmark_name == "fig_1_1", r1[0].bookmark_name)
        check("px_w 不为 None", r1[0].px_w is not None, str(r1[0].px_w))
        check("px_h 不为 None", r1[0].px_h is not None, str(r1[0].px_h))
        print(f"    像素尺寸: {r1[0].px_w}x{r1[0].px_h}")
        print(f"    解析路径: {r1[0].path_resolved}")

    # --- 测试2：alt "插图" → W-IMG-01 ---
    print("\n=== 测试2：不匹配图X-Y模式 → W-IMG-01 ===")
    c2 = IssueCollector()
    tokens2 = [
        ImageToken(
            alt_raw="插图",
            path_raw="figures/1-1-城际动车组谱系.png",
            source_line=10,
        )
    ]
    r2 = resolve_figures(
        tokens2, str(_FIXTURES_DIR), str(_FIGURES_DIR), c2
    )
    check("返回 1 个 FigureIR", len(r2) == 1, f"实际 {len(r2)}")
    if r2:
        check("figure_id 以 fig_ 开头", r2[0].figure_id.startswith("fig_"), r2[0].figure_id)
        check("caption_text='插图'", r2[0].caption_text == "插图", r2[0].caption_text)
    check("有 W-IMG-01", any(i.code == "W-IMG-01" for i in c2),
          "不匹配「图X-Y」应产 W-IMG-01")
    if not any(i.code == "W-IMG-01" for i in c2):
        print(f"    实际 issues: {[(i.code, i.message[:50]) for i in c2]}")

    # --- 测试3：网络 URL ---
    print("\n=== 测试3：网络 URL → W-IMG-08 ===")
    c3 = IssueCollector()
    tokens3 = [
        ImageToken(
            alt_raw="图1-1 测试图",
            path_raw="https://example.com/img.png",
            source_line=5,
        )
    ]
    r3 = resolve_figures(tokens3, str(_FIXTURES_DIR), None, c3)
    check("返回 1 个 FigureIR", len(r3) == 1, f"实际 {len(r3)}")
    if r3:
        check("file_exists=False", not r3[0].file_exists, str(r3[0].file_exists))
        check("px_w=None", r3[0].px_w is None, str(r3[0].px_w))
    check("有 W-IMG-08", any(i.code == "W-IMG-08" for i in c3),
          "网络 URL 应产 W-IMG-08")

    # --- 测试4：文件不存在 → E-IMG-01 ---
    print("\n=== 测试4：文件不存在 → E-IMG-01 ===")
    c4 = IssueCollector()
    tokens4 = [
        ImageToken(
            alt_raw="图9-9 不存在的图",
            path_raw="figures/不存在的文件.png",
            source_line=99,
        )
    ]
    r4 = resolve_figures(tokens4, str(_FIXTURES_DIR), None, c4)
    check("返回 1 个 FigureIR", len(r4) == 1, f"实际 {len(r4)}")
    if r4:
        check("file_exists=False", not r4[0].file_exists, str(r4[0].file_exists))
    check("有 E-IMG-01", any(i.code == "E-IMG-01" for i in c4),
          "文件不存在应产 E-IMG-01")

    # --- 测试5：多图 + 宽图分辨率警告 ---
    print("\n=== 测试5：多图处理 + 分辨率警告 ===")
    c5 = IssueCollector()
    tokens5 = [
        ImageToken(
            alt_raw="图1-1 城际动车组产品谱系图",
            path_raw="figures/1-1-城际动车组谱系.png",
            source_line=29,
        ),
        ImageToken(
            alt_raw="图2-1 城市轨道信号系统市场份额分布",
            path_raw="figures/2-1-信号系统市场份额.png",
            source_line=49,
        ),
        ImageToken(
            alt_raw="图3-1 海外出海项目地理分布",
            path_raw="figures/3-1-出海项目分布.png",
            source_line=61,
        ),
    ]
    r5 = resolve_figures(
        tokens5, str(_FIXTURES_DIR), str(_FIGURES_DIR), c5
    )
    check("返回 3 个 FigureIR", len(r5) == 3, f"实际 {len(r5)}")
    # 图3-1 像素 800×400 → 应触发 W-IMG-02（<1102px）
    check("有 W-IMG-02（图3-1 宽800<1102）",
          any(i.code == "W-IMG-02" for i in c5),
          f"实际 issues: {[(i.code,) for i in c5]}")
    # 图2-1 像素 1200×1500 → 应触发 I-IMG-03（1102-1653）
    check("有 I-IMG-03（图2-1 宽1200∈[1102,1654)）",
          any(i.code == "I-IMG-03" for i in c5),
          f"实际 issues: {[(i.code,) for i in c5]}")
    print(f"    图1-1: {r5[0].px_w}x{r5[0].px_h}")
    print(f"    图2-1: {r5[1].px_w}x{r5[1].px_h}")
    print(f"    图3-1: {r5[2].px_w}x{r5[2].px_h}")

    # --- 测试6：空列表 ---
    print("\n=== 测试6：空列表 ===")
    c6 = IssueCollector()
    r6 = resolve_figures([], str(_FIXTURES_DIR), None, c6)
    check("返回空列表", len(r6) == 0, f"实际 {len(r6)}")
    check("无 issues", len(list(c6)) == 0, f"实际 {len(list(c6))}")

    # --- 测试7：图号含冒号分隔 ---
    print("\n=== 测试7：alt 含冒号分隔 ===")
    c7 = IssueCollector()
    tokens7 = [
        ImageToken(
            alt_raw="图1-1：城际动车组产品谱系图",
            path_raw="figures/1-1-城际动车组谱系.png",
            source_line=29,
        )
    ]
    r7 = resolve_figures(
        tokens7, str(_FIXTURES_DIR), str(_FIGURES_DIR), c7
    )
    check("返回 1 个 FigureIR", len(r7) == 1, f"实际 {len(r7)}")
    if r7:
        check("figure_id='1-1'（冒号分隔）", r7[0].figure_id == "1-1", r7[0].figure_id)
        # 注意：冒号后跟空格，RE_FIG_ALT 中 [：:][ 　]* 会消耗冒号+空格
        check(
            "caption_text 不含前导冒号",
            not r7[0].caption_text.startswith("："),
            r7[0].caption_text,
        )
        print(f"    caption_text: {r7[0].caption_text!r}")

    # --- 测试8：_resolve_image_path 辅助函数 ---
    print("\n=== 测试8：_resolve_image_path ===")
    # 存在的文件
    p, svg = _resolve_image_path(
        "figures/1-1-城际动车组谱系.png",
        str(_FIXTURES_DIR),
        str(_FIGURES_DIR),
    )
    check("相对路径解析成功", p is not None, str(p))
    check("非 SVG 协商", not svg, str(svg))
    # 不存在的文件
    p2, svg2 = _resolve_image_path(
        "不存在.png", str(_FIXTURES_DIR), None
    )
    check("不存在的文件返回 None", p2 is None, str(p2))
    check("不存在的文件 svg=False", not svg2, str(svg2))

    # --- 测试9：PNG IHDR 读取 ---
    print("\n=== 测试9：_read_png_pixel_size ===")
    real_png = str(_FIGURES_DIR / "1-1-城际动车组谱系.png")
    w, h = _read_png_pixel_size(real_png)
    check("实际 PNG 像素宽读取成功", w is not None and w > 0, str(w))
    check("实际 PNG 像素高读取成功", h is not None and h > 0, str(h))
    print(f"    读取结果: {w}x{h}")
    # 非 PNG 文件
    w2, h2 = _read_png_pixel_size(__file__)  # 本 .py 文件不是 PNG
    check("非 PNG 文件返回 None", w2 is None and h2 is None, f"({w2}, {h2})")
    # 不存在的文件
    w3, h3 = _read_png_pixel_size(str(_FIXTURES_DIR / "不存在.png"))
    check("不存在文件返回 None", w3 is None and h3 is None, f"({w3}, {h3})")

    # --- 汇总 ---
    print(f"\n{'='*50}")
    print(f"通过: {passed}, 失败: {failed}")
    print(f"{'='*50}")

    if failed > 0:
        sys.exit(1)
    else:
        print("全部 figures 自检通过！")
