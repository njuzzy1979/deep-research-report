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

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

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
    png_files = sorted(fig_dir.glob("*.png"))
    if not png_files:
        results["passed"] = True
        results["items"].append({"file": "(无PNG文件)", "width_px": 0, "height_px": 0, "dpi_x": 0, "dpi_y": 0, "dpi_ok": True, "printable": True})
        return results
    for png in png_files:
        img = Image.open(png)
        dpi = img.info.get("dpi", (0, 0))
        w, h = img.size
        item = {
            "file": png.name,
            "width_px": w,
            "height_px": h,
            "dpi_x": dpi[0] if dpi[0] else 0,
            "dpi_y": dpi[1] if dpi[1] else 0,
            "dpi_ok": (dpi[0] >= 300 and dpi[1] >= 300) if dpi[0] and dpi[1] else False,
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
    png_files = sorted(fig_dir.glob("*.png"))
    if not png_files:
        results["passed"] = True
        results["items"].append({"file": "(无PNG文件)", "violation_pct": 0.0, "passed": True})
        return results
    for png in png_files:
        img = Image.open(png).convert("RGB")
        pixels = np.array(img).reshape(-1, 3)
        n_sample = min(2000, len(pixels))
        rng = np.random.default_rng()
        sample = pixels[rng.choice(len(pixels), n_sample, replace=False)]
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
    if not rows:
        return {"passed": False, "error": "color-registry.csv 为空"}
    required_cols = {"concept", "color_hex", "first_used_fig"}
    actual_cols = set(rows[0].keys())
    missing_cols = required_cols - actual_cols
    if missing_cols:
        return {"passed": False, "error": f"缺少必填列: {missing_cols}"}
    # 检查 color_hex 是否在许可色板中
    invalid_colors = [r for r in rows if r.get("color_hex", "").upper().strip() not in ALLOWED_COLORS_HEX]
    return {
        "passed": len(invalid_colors) == 0,
        "entry_count": len(rows),
        "invalid_colors": [r["concept"] for r in invalid_colors],
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="图表质量自动检查脚本")
    ap.add_argument("--figures-dir", default="research/figures", help="图表目录路径")
    ap.add_argument("--dpi", action="store_true", help="仅DPI检查")
    ap.add_argument("--colors", action="store_true", help="仅颜色检查")
    ap.add_argument("--registry", action="store_true", help="仅注册表检查")
    args = ap.parse_args()

    run_all = not (args.dpi or args.colors or args.registry)

    exit_code = 0
    if run_all or args.dpi:
        r = check_dpi(args.figures_dir)
        print(f"DPI检查: {'PASS' if r['passed'] else 'FAIL'}")
        for item in r["items"]:
            flag = "[OK]" if (item["dpi_ok"] and item["printable"]) else "[FAIL]"
            print(f"  {flag} {item['file']}: {item['width_px']}x{item['height_px']}px, DPI={item['dpi_x']}")
        if not r["passed"]:
            exit_code = 1

    if run_all or args.colors:
        r = check_colors(args.figures_dir)
        print(f"颜色检查: {'PASS' if r['passed'] else 'FAIL'}")
        for item in r["items"]:
            flag = "[OK]" if item["passed"] else "[FAIL]"
            print(f"  {flag} {item['file']}: 违规像素 {item['violation_pct']}%")
        if not r["passed"]:
            exit_code = 1

    if run_all or args.registry:
        r = check_registry(args.figures_dir)
        print(f"注册表检查: {'PASS' if r['passed'] else 'FAIL'} — {r}")
        if not r["passed"]:
            exit_code = 2

    sys.exit(exit_code)
