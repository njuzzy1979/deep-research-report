# 图表质量检查清单

> 来源：design/chart-quality-constraints/00-chart-quality-design.md
> 用途：阶段6（架构图）和阶段7（数据图表）的质量门槛检查
> 标注：🤖 = 自动化可检查 | 👤 = 人工检查 | 🛑 = 阻塞性门槛

---

## 一、阶段6 架构图质量检查（5+3=8 项）

### 原有项（保留）

| # | 检查项 | 方式 | 阻塞 |
|---|--------|------|------|
| 1 | 总览图至少 1 张完成（`.drawio` + `.svg` + `.png` 三件套） | 🤖 | 🛑 |
| 2 | 每个核心分析章节至少 1 张架构图草图 | 👤 | — |
| 3 | 架构图之间逻辑一致（同一对象名称统一） | 👤 | — |
| 4 | 所有架构图有逻辑或来源标注 | 👤 | — |
| 5 | 所有 PNG 均已验证达到 300dpi | 🤖 | 🛑 |

### 新增项（Q-20）

| # | 检查项 | 方式 | 阻塞 | 操作指南 |
|---|--------|------|------|---------|
| 6 | **颜色映射注册表完整性**：`research/figures/color-registry.csv` 已创建并覆盖所有核心架构图的节点，同一概念在不同图中颜色一致 | 🤖 | 🛑 | 检查：grep 所有 `.drawio` 中的颜色，与注册表比对。不一致时记录偏差 |
| 7 | **配色合规**：所有架构图仅使用灰度色板（#000000/#333333/#555555/#777777/#999999/#BBBBBB/#DDDDDD/#F2F2F2/#FFFFFF），强调色仅 #D62728 且全图 ≤3 处 | 👤 | — | 抽查 2-3 张图 |
| 8 | **PNG 分辨率达标**：所有 PNG 宽度 ≥1102px（对应 14cm@200dpi 最低阈值；≤1102px 时 300dpi 下不足 9pt 可读性）。检查方式同已有 W-IMG-02 | 🤖 | 🛑 | 用 PIL 读 PNG 尺寸：`Image.open(p).size[0] >= 1102` |

---

## 二、阶段7 数据图表质量检查（9+3=12 项）

### 原有项（保留）

| # | 检查项 | 方式 | 阻塞 |
|---|--------|------|------|
| 1 | 每章开头有"本章结论"，末尾有"对主论点的贡献" | 👤 | — |
| 2 | 所有 C/D 级来源的事实已标注强度 | 👤 | — |
| 3 | 所有图表已在正文中引用（图在首次引用的段落之后） | 👤 | — |
| 4 | 每章数据图表与文字内容一致 | 👤 | — |
| 5 | 本章对应的专题卡片已全部核对 | 👤 | — |
| 6 | 未出现台账中标记为"错误/误导"的主张 | 👤 | — |
| 7 | 证据密度检查 | 👤 | — |
| 8 | 建议可操作性检查 | 👤 | — |
| 9 | 摘要自足性检查 | 👤 | — |

### 新增项（Q-21, Q-22）

| # | 检查项 | 方式 | 阻塞 | 操作指南 |
|---|--------|------|------|---------|
| 10 | **matplotlib rcParams 已加载**：执行图表的脚本/notebook 中以 `plt.style.use('design/chart-quality-constraints/matplotlib-report-style.mplstyle')` 开头 | 🤖 | 🛑 | 检查：grep 所有 `.py`/`.ipynb` 出图脚本，确认含 `plt.style.use` 且指向正确的 `.mplstyle` 路径 |
| 11 | **图表类型合规**：每张数据图表的类型在决策表"首选"或"次选"列中，或对"禁止"类型有书面解释 | 👤 | 🛑 | 参考决策表（主设计文档 §3.4），抽查所有数据图。如使用了禁止类型（3D 等），必须提供解释 |
| 12 | **色盲友好检查**：饼图使用了阴影线（hatch）区分扇区，多系列折线图使用了不同线型+dash 而不仅靠颜色 | 👤 | — | 纯灰度折线图除外（灰度值差异已足够区分，但需确保 ≥3 档灰度差） |

---

## 三、图表质量自动检查脚本

### 脚本1：`scripts/chart_checks.py`

```python
"""图表质量自动检查脚本。

用法：
    python scripts/chart_checks.py --figures-dir research/figures/
    python scripts/chart_checks.py --dpi        # 仅DPI检查
    python scripts/chart_checks.py --colors     # 仅颜色检查
    python scripts/chart_checks.py --registry   # 仅注册表检查
"""

import sys
import csv
from pathlib import Path
from collections import defaultdict

try:
    from PIL import Image
except ImportError:
    print("错误：需要 Pillow 库。pip install Pillow")
    sys.exit(1)


# 许可色板（Q-01, Q-02）
ALLOWED_COLORS_HEX = {
    "#000000", "#333333", "#555555", "#777777",
    "#999999", "#BBBBBB", "#DDDDDD", "#F2F2F2",
    "#FFFFFF", "#D62728",
}


def _hex_to_rgb(h: str):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _color_distance(rgb1, rgb2):
    return ((rgb1[0] - rgb2[0]) ** 2 + (rgb1[1] - rgb2[1]) ** 2 + (rgb1[2] - rgb2[2]) ** 2) ** 0.5


ALLOWED_RGB = [_hex_to_rgb(h) for h in ALLOWED_COLORS_HEX]


def check_dpi(figures_dir: str) -> dict:
    """检查所有PNG的DPI和分辨率"""
    fig_dir = Path(figures_dir)
    results = {"passed": True, "items": []}
    for png in sorted(fig_dir.glob("*.png")):
        img = Image.open(png)
        dpi = img.info.get("dpi", (0, 0))
        w, h = img.size
        item = {
            "file": png.name,
            "width_px": w,
            "height_px": h,
            "dpi_x": dpi[0],
            "dpi_y": dpi[1],
            "dpi_ok": dpi[0] >= 300 and dpi[1] >= 300,
            "printable": w >= 1102,  # Q-11: 14cm@200dpi最低
        }
        if not item["dpi_ok"] or not item["printable"]:
            results["passed"] = False
        results["items"].append(item)
    return results


def check_colors(figures_dir: str) -> dict:
    """检查所有PNG的配色合规（采样检查）"""
    import numpy as np
    fig_dir = Path(figures_dir)
    results = {"passed": True, "items": []}
    for png in sorted(fig_dir.glob("*.png")):
        img = Image.open(png).convert("RGB")
        pixels = np.array(img).reshape(-1, 3)
        n_sample = min(2000, len(pixels))
        sample = pixels[np.random.choice(len(pixels), n_sample, replace=False)]
        violations = []
        for px in sample:
            r, g, b = int(px[0]), int(px[1]), int(px[2])
            if r == g == b == 255:  # 纯白豁免
                continue
            ok = any(_color_distance((r, g, b), allowed) < 30 for allowed in ALLOWED_RGB)
            if not ok:
                violations.append(f"#{r:02X}{g:02X}{b:02X}")
        violation_pct = len(violations) / n_sample * 100
        item = {
            "file": png.name,
            "violation_pct": round(violation_pct, 1),
            "passed": violation_pct < 2.0,
        }
        if not item["passed"]:
            results["passed"] = False
        results["items"].append(item)
    return results


def check_registry(figures_dir: str) -> dict:
    """检查 color-registry.csv 完整性"""
    reg_path = Path(figures_dir) / "color-registry.csv"
    if not reg_path.exists():
        return {"passed": False, "error": "color-registry.csv 不存在"}
    rows = []
    with open(reg_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    required_cols = {"concept", "color_hex", "first_used_fig"}
    actual_cols = set(rows[0].keys()) if rows else set()
    missing_cols = required_cols - actual_cols
    if missing_cols:
        return {"passed": False, "error": f"缺少必填列: {missing_cols}"}
    # 检查 color_hex 是否在许可色板中
    invalid_colors = [r for r in rows if r.get("color_hex", "").upper() not in ALLOWED_COLORS_HEX]
    return {
        "passed": len(invalid_colors) == 0,
        "entry_count": len(rows),
        "invalid_colors": [r["concept"] for r in invalid_colors],
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--figures-dir", default="research/figures")
    ap.add_argument("--dpi", action="store_true")
    ap.add_argument("--colors", action="store_true")
    ap.add_argument("--registry", action="store_true")
    args = ap.parse_args()

    run_all = not (args.dpi or args.colors or args.registry)

    exit_code = 0
    if run_all or args.dpi:
        r = check_dpi(args.figures_dir)
        print(f"DPI检查: {'PASS' if r['passed'] else 'FAIL'}")
        for item in r["items"]:
            flag = "✅" if (item["dpi_ok"] and item["printable"]) else "❌"
            print(f"  {flag} {item['file']}: {item['width_px']}x{item['height_px']}px, DPI={item['dpi_x']}")
        if not r["passed"]: exit_code = 1

    if run_all or args.colors:
        r = check_colors(args.figures_dir)
        print(f"颜色检查: {'PASS' if r['passed'] else 'FAIL'}")
        for item in r["items"]:
            flag = "✅" if item["passed"] else "❌"
            print(f"  {flag} {item['file']}: 违规像素 {item['violation_pct']}%")
        if not r["passed"]: exit_code = 1

    if run_all or args.registry:
        r = check_registry(args.figures_dir)
        print(f"注册表检查: {'PASS' if r['passed'] else 'FAIL'} — {r}")
        if not r["passed"]: exit_code = 2

    sys.exit(exit_code)
```

---

## 四、drawio 出图 prompt 约束注入模板

在调用 `mcp__drawio__create_diagram` 时，将以下内容追加到 prompt 末尾：

```
[STYLE CONSTRAINTS — 严格遵守]
1. 配色：仅使用黑色(#000000)、深灰(#333333)、灰色(#555555)、浅灰(#999999)、
   极浅灰(#DDDDDD)、白色(#FFFFFF)。不同层级/模块通过灰度深度区分，不用彩色。
2. 强调色：如必须高亮，仅使用暗红(#D62728)，全图最多 3 处。不用其他彩色。
3. 字体：所有文本元素字号 ≥12px(约9pt)。标题字号 ≥14px(约10.5pt)。
4. 边框：节点边框 1pt、#333333。箭头线宽 1.5pt、#000000，箭头端点实心三角。
5. 形状：同层级/同类别节点使用相同形状。
6. 背景：纯白 #FFFFFF。不做渐变、阴影、或透明效果。
7. 图例：若图中有 >2 种灰度/形状，必须在图中添加图例。

[OUTPUT CHECKLIST — 生成后自查]
- 整图配色是否在灰度+暗红范围内？
- 文字是否 ≥9pt？
- 图例是否存在？
- 背景是否纯白？
```
