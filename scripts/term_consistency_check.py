#!/usr/bin/env python3
"""术语一致性检查脚本。

输入：当前章草稿 Markdown 文件 + research/glossary.md（阶段 5 产出）
输出：JSON 格式检查结果（pass/fail + 违规项列表）

检查项：
  1. alias 泄露检测 —— 正文是否使用了 glossary 中标记为 banned_forms 的变体
  2. 原创概念保真度 —— preferred_form 是否被逐字使用

用法：
  python term_consistency_check.py <draft.md> <glossary.md> [--json]
  python term_consistency_check.py --help
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def extract_yaml_glossary(glossary_path: str) -> list[dict[str, Any]]:
    """从 glossary.md 中提取 YAML 术语元数据。

    返回 glossary 条目列表，每项为 dict。
    """
    content = Path(glossary_path).read_text(encoding="utf-8")

    # 提取文件中最后一个 ```yaml ... ``` 代码块
    yaml_pattern = re.compile(r"```yaml\s*\n(.*?)```", re.DOTALL)
    matches = yaml_pattern.findall(content)
    if not matches:
        raise ValueError(
            f"{glossary_path} 中未找到 YAML 代码块，"
            f"请确认文件包含 ```yaml ... ``` 格式的术语元数据"
        )

    yaml_text = matches[-1]
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "需要 PyYAML 库。请执行: pip install pyyaml"
        )

    data = yaml.safe_load(yaml_text)
    if not data or "glossary" not in data:
        raise ValueError(
            f"{glossary_path} 中 YAML 数据不包含 'glossary' 键"
        )
    return data["glossary"]


def extract_body_text(draft_path: str) -> str:
    """从草稿 Markdown 文件中提取正文文本。

    移除 YAML front matter、代码块、HTML 注释，保留纯正文。
    """
    raw = Path(draft_path).read_text(encoding="utf-8")

    # 移除 YAML front matter (--- ... ---)
    raw = re.sub(r"^---\s*\n.*?^---\s*\n", "", raw, flags=re.DOTALL | re.MULTILINE)

    # 移除代码块
    raw = re.sub(r"```.*?```", "", raw, flags=re.DOTALL)

    # 移除 HTML 注释
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)

    # 移除 Markdown 图片语法（保留 alt text 无意义）
    raw = re.sub(r"!\[.*?\]\(.*?\)", "", raw)

    # 移除 Markdown 链接，保留链接文本
    raw = re.sub(r"\[([^\]]+)\]\(.*?\)", r"\1", raw)

    # 移除引用块前缀
    raw = re.sub(r"^>\s?", "", raw, flags=re.MULTILINE)

    # 移除行内代码
    raw = re.sub(r"`[^`]+`", "", raw)

    # 压缩空白
    raw = re.sub(r"\s+", " ", raw)

    return raw.strip()


def check_banned_forms(
    body_text: str, entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """检测正文中是否出现了 banned_forms 中的禁止变体。

    返回违规项列表。
    """
    violations: list[dict[str, Any]] = []
    for entry in entries:
        banned = entry.get("banned_forms", [])
        if not banned:
            continue
        term_id = entry.get("term_id", "UNKNOWN")
        preferred = entry.get("preferred_form", "")
        for banned_form in banned:
            # 使用词边界匹配（如果 banned_form 包含中文则回退到子串匹配）
            if re.search(r"[一-鿿]", banned_form):
                # 中文：子串匹配
                if banned_form in body_text:
                    violations.append({
                        "term_id": term_id,
                        "preferred_form": preferred,
                        "check_type": "banned_form",
                        "banned_form_found": banned_form,
                        "message": (
                            f"正文中出现了术语 {term_id} 的禁止变体 "
                            f"\"{banned_form}\"，应使用 preferred_form "
                            f"\"{preferred}\""
                        ),
                    })
            else:
                # 英文/缩写：词边界匹配
                pattern = re.compile(
                    r"(?<![a-zA-Z])" + re.escape(banned_form) + r"(?![a-zA-Z])"
                )
                if pattern.search(body_text):
                    violations.append({
                        "term_id": term_id,
                        "preferred_form": preferred,
                        "check_type": "banned_form",
                        "banned_form_found": banned_form,
                        "message": (
                            f"正文中出现了术语 {term_id} 的禁止变体 "
                            f"\"{banned_form}\"，应使用 preferred_form "
                            f"\"{preferred}\""
                        ),
                    })
    return violations


def check_preferred_form_fidelity(
    body_text: str, entries: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """检测原创核心概念的 preferred_form 是否在正文中被使用。

    对于 scope="全报告" 的原创概念，检查 preferred_form 的基础形式
    （不含括号内英文部分）是否至少出现一次。
    如果正文中出现了接近但不完全匹配的变体，报告为非逐字引用。
    """
    violations: list[dict[str, Any]] = []

    for entry in entries:
        category = entry.get("category", "")
        if category != "原创核心概念":
            continue

        term_id = entry.get("term_id", "UNKNOWN")
        preferred = entry.get("preferred_form", "")

        # 提取基础中文形式（去除括号内的英文/缩写部分）
        base_form = re.sub(r"\s*\([^)]*\)", "", preferred).strip()

        # 检查 base_form 是否在正文中出现
        if base_form not in body_text:
            # 检查是否有接近的变体（如缺少部分字词）
            # 拆分为词元，检查是否有至少 80% 的 n-gram 匹配
            alt_form_found = _find_close_match(base_form, body_text)

            violations.append({
                "term_id": term_id,
                "preferred_form": preferred,
                "check_type": "preferred_form_missing",
                "expected_form": base_form,
                "actual_form_found": alt_form_found,
                "message": (
                    f"原创核心概念 {term_id} 的 preferred_form "
                    f"\"{base_form}\" 未在正文中逐字出现"
                    + (
                        f"，发现近似形式 \"{alt_form_found}\""
                        if alt_form_found
                        else ""
                    )
                ),
            })

    return violations


def _find_close_match(
    base_form: str, body_text: str, min_overlap: float = 0.6
) -> str | None:
    """在正文中查找与 base_form 最接近的匹配。

    使用字符级 3-gram 重叠率做近似匹配。
    返回最接近的匹配文本片段，或 None。
    """
    if len(base_form) < 4:
        return None

    # 提取 base_form 的 3-gram 集合
    base_ngrams: set[str] = set()
    for i in range(len(base_form) - 2):
        base_ngrams.add(base_form[i : i + 3])

    if not base_ngrams:
        return None

    # 在正文中滑动窗口，查找最高重叠率
    best_match: str | None = None
    best_ratio: float = 0.0
    window_min = max(3, len(base_form) // 2)
    window_max = min(len(body_text), len(base_form) * 2)

    for window_size in range(window_min, window_max + 1, 3):
        for start in range(0, len(body_text) - window_size + 1, window_size // 3):
            candidate = body_text[start : start + window_size]
            candidate_ngrams: set[str] = set()
            for i in range(len(candidate) - 2):
                candidate_ngrams.add(candidate[i : i + 3])

            if not candidate_ngrams:
                continue

            overlap = len(base_ngrams & candidate_ngrams) / len(base_ngrams)
            if overlap > best_ratio and overlap >= min_overlap:
                best_ratio = overlap
                best_match = candidate
                if overlap > 0.85:
                    # 高置信度匹配，提前返回
                    return best_match

    return best_match if best_ratio >= min_overlap else None


def run_check(draft_path: str, glossary_path: str) -> dict[str, Any]:
    """执行术语一致性检查并返回结构化结果。"""
    entries = extract_yaml_glossary(glossary_path)
    body_text = extract_body_text(draft_path)

    banned_violations = check_banned_forms(body_text, entries)
    form_violations = check_preferred_form_fidelity(body_text, entries)

    all_violations = banned_violations + form_violations
    passed = len(all_violations) == 0

    return {
        "status": "pass" if passed else "fail",
        "draft_file": str(Path(draft_path).resolve()),
        "glossary_file": str(Path(glossary_path).resolve()),
        "glossary_entry_count": len(entries),
        "violation_count": len(all_violations),
        "banned_form_violations": len(banned_violations),
        "preferred_form_violations": len(form_violations),
        "violations": all_violations,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="术语一致性检查 —— 检测草稿中的术语是否与 glossary.md 一致",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python term_consistency_check.py draft.md glossary.md
  python term_consistency_check.py draft.md glossary.md --json
        """.strip(),
    )
    parser.add_argument(
        "draft",
        help="当前章草稿 Markdown 文件路径",
    )
    parser.add_argument(
        "glossary",
        help="research/glossary.md 文件路径（阶段 5 产出）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="以 JSON 格式输出结果（默认）",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="以人类可读文本格式输出结果",
    )

    args = parser.parse_args()

    try:
        result = run_check(args.draft, args.glossary)
    except FileNotFoundError as e:
        print(json.dumps({
            "status": "error",
            "error": f"文件未找到: {e}",
        }, ensure_ascii=False, indent=2))
        sys.exit(2)
    except (ValueError, ImportError) as e:
        print(json.dumps({
            "status": "error",
            "error": str(e),
        }, ensure_ascii=False, indent=2))
        sys.exit(2)

    if args.text:
        _print_text_result(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

    sys.exit(0 if result["status"] == "pass" else 1)


def _print_text_result(result: dict[str, Any]) -> None:
    """以人类可读格式输出结果。"""
    status = result["status"]
    status_icon = "[PASS]" if status == "pass" else "[FAIL]"
    print(f"{status_icon} 术语一致性检查")
    print(f"  草稿文件: {result['draft_file']}")
    print(f"  术语表文件: {result['glossary_file']}")
    print(f"  术语条目总数: {result['glossary_entry_count']}")
    print(f"  违规项总数: {result['violation_count']}")
    print(f"    - banned_form 违规: {result['banned_form_violations']}")
    print(f"    - preferred_form 违规: {result['preferred_form_violations']}")
    print()

    if result["violations"]:
        for i, v in enumerate(result["violations"], 1):
            print(f"  违规 #{i}: [{v['term_id']}] {v['check_type']}")
            print(f"    {v['message']}")
            print()


if __name__ == "__main__":
    main()
