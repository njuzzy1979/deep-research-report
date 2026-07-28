#!/usr/bin/env python3
"""Phase A 确认式 Markdown → JSON 落盘转换器（跨模型兼容性优化方案 §C4 手段 1/2）。

背景（方案 §C4）：`chapter_auditor_agent` 在 `phase_a_mode=confirm`（`derive_phase_a_mode`
判定 `max_output_tokens<16000` 时触发，见 ``scripts/model_profile.py``）下，Phase A
书写形态改为对 `auditor_contract.json` 每个维度输出一个 Markdown 二级标题 + 一行
`confirm` 或 `adjust: <text>`（对弱模型友好）；落盘/校验形态则是 JSON，需符合
``schemas/auditor-phase-a.schema.json``：

    {"ch01": {"outline_coverage": {"mode": "confirm"},
               "strong_claim": {"mode": "adjust", "text": "..."}}}

本脚本承担"书写形态 -> 落盘形态"的转换，并在极端弱模型仍超限时支持**分批兜底**
（方案 §C4 手段 2）——`auditor_contract.json` 的 `batch_grouping` 字段按严重度把
29 个维度拆成 3 批，每批分别落盘为 `chXX-precommit-batch{1,2,3}.md`，首行须为
HTML 注释元数据 `<!-- phase=A batch=N chapter=chXX dims=<count> -->`。``--merge``
读取各批次文件的元数据，核对：

    - 元数据声明的 phase/chapter 与调用方一致
    - 批次号覆盖 1/2/3 且不重复（不允许缺批次）
    - 元数据声明的 dims 数与实际解析出的维度小节数一致
    - 该批次实际维度 id 集合与 `batch_grouping` 声明的对应子集一致

任一项不满足 -> 报错，**不静默拼接**（方案原文纪律：批次不完整不能悄悄合并）。

维度 id 合法性：全部维度 id 取自 `agents/contracts/auditor_contract.json` 的
`dimensions` + `proposal_extra`（当前共 29 个）。出现契约未声明的维度 id 一律报错。

产出校验复用 ``scripts/schema_validate.py`` 的 ``load_schema`` / ``validate_instance``，
不重复实现 JSON Schema 校验逻辑。

用法：
    # 单文件（free 或非分批确认式）转换
    python scripts/phase_a_to_json.py research/chapter-reports/chXX-precommit.md --chapter chXX --json

    # 分批合并（proposal 档 29 维度超限时）
    python scripts/phase_a_to_json.py research/chapter-reports/chXX-precommit-batch1.md \\
        research/chapter-reports/chXX-precommit-batch2.md \\
        research/chapter-reports/chXX-precommit-batch3.md \\
        --chapter chXX --merge --json

    # 附加 --out 落盘 JSON
    python scripts/phase_a_to_json.py chXX-precommit.md --chapter chXX --out chXX-precommit.json

退出码：0 = 转换成功且通过 schema 校验；
       1 = 内容级校验失败（未知维度 id / 批次不完整 / 产出未通过 schema 校验）；
       2 = 文件不存在 / 读取或解析异常 / 依赖模块不可用。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

# Windows 中文环境编码兼容（沿用 scripts/contract_check.py:42-48 同款模式）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# schema 校验复用 schema_validate.py，不重复实现校验逻辑
# （沿用 scripts/model_profile.py:62-66 同款容错导入模式）。
try:
    import schema_validate as sv
except ImportError:
    sv = None

# ASCII 替代符号（避免 emoji 在 GBK 控制台崩溃）
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUDITOR_CONTRACT_PATH = _PROJECT_ROOT / "agents" / "contracts" / "auditor_contract.json"

# 章节标识格式，与 schemas/auditor-phase-a.schema.json 的 propertyNames.pattern 一致
CHAPTER_ID_PATTERN = re.compile(r"^ch\d{2,3}$")

# 维度标题：Markdown 二级标题 `### <维度id>`
HEADING_PATTERN = re.compile(r"^###\s+(\S+)\s*$", re.MULTILINE)

# adjust 行：`adjust: <一句话>` （允许中英文冒号；允许冒号后为空，交由调用方判空报错）
ADJUST_LINE_PATTERN = re.compile(r"^adjust\s*[:：]\s*(.*)$")

# 批次元数据 HTML 注释：`<!-- phase=A batch=1 chapter=ch01 dims=9 -->`
BATCH_META_PATTERN = re.compile(
    r"phase=(?P<phase>\S+)\s+batch=(?P<batch>\d+)\s+chapter=(?P<chapter>ch\d{2,3})\s+dims=(?P<dims>\d+)"
)

BATCH_KEY_BY_NUM = {1: "batch1_high", 2: "batch2_mid", 3: "batch3_low"}


def read_text(path: str) -> str:
    """二进制安全读取，处理 BOM / CRLF（与 contract_check.py:126-134 同款模式）。"""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def load_known_dimension_ids(contract_path: Optional[Path] = None) -> set:
    """从 auditor_contract.json 的 dimensions + proposal_extra 读取全部合法维度 id（当前 29 个）。"""
    path = contract_path or AUDITOR_CONTRACT_PATH
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    contract = json.loads(raw.decode("utf-8"))
    ids = [d["id"] for d in contract["dimensions"]]
    ids += [d["id"] for d in contract.get("proposal_extra", [])]
    return set(ids)


def load_batch_grouping(contract_path: Optional[Path] = None) -> dict:
    """读取 auditor_contract.json 的 batch_grouping 字段（分批兜底的严重度分组声明）。"""
    path = contract_path or AUDITOR_CONTRACT_PATH
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    contract = json.loads(raw.decode("utf-8"))
    return contract.get("batch_grouping", {})


def parse_markdown_dimensions(text: str) -> dict:
    """解析 Phase A 确认式 Markdown（`### <维度id>` + `confirm`/`adjust: <text>`）。

    返回 {dim_id: {"mode": "confirm"}} 或 {dim_id: {"mode": "adjust", "text": "..."}}。
    格式错误（缺内容行 / adjust 缺文本 / 维度重复）一律 raise ValueError。
    """
    headings = list(HEADING_PATTERN.finditer(text))
    dims: dict = {}
    for i, m in enumerate(headings):
        dim_id = m.group(1)
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[start:end]

        mode_line = None
        for line in body.splitlines():
            stripped = line.strip()
            if stripped:
                mode_line = stripped
                break

        if mode_line is None:
            raise ValueError(f"维度 '{dim_id}' 标题后缺少 confirm/adjust 内容行")

        if dim_id in dims:
            raise ValueError(f"维度 '{dim_id}' 重复出现")

        if mode_line == "confirm":
            dims[dim_id] = {"mode": "confirm"}
            continue

        adjust_match = ADJUST_LINE_PATTERN.match(mode_line)
        if adjust_match:
            text_val = adjust_match.group(1).strip()
            if not text_val:
                raise ValueError(f"维度 '{dim_id}' 的 adjust 行缺少说明文本")
            dims[dim_id] = {"mode": "adjust", "text": text_val}
            continue

        raise ValueError(
            f"维度 '{dim_id}' 的内容行既非 'confirm' 也非 'adjust: <text>'：{mode_line!r}"
        )

    return dims


def parse_batch_metadata(text: str) -> Optional[dict]:
    """解析文件首行的批次元数据 HTML 注释。无该注释返回 None（非分批场景合法）。"""
    first_line = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            first_line = stripped
            break
    if not first_line or not first_line.startswith("<!--"):
        return None
    m = BATCH_META_PATTERN.search(first_line)
    if not m:
        return None
    return {
        "phase": m.group("phase"),
        "batch": int(m.group("batch")),
        "chapter": m.group("chapter"),
        "dims": int(m.group("dims")),
    }


def parse_single_file(path: str, known_ids: set) -> dict:
    """解析单份（非分批）Phase A Markdown 文件，返回 {dim_id: {mode, text?}}。"""
    text = read_text(path)
    dims = parse_markdown_dimensions(text)
    unknown = sorted(set(dims) - known_ids)
    if unknown:
        raise ValueError(f"{path}: 出现契约未声明的维度 id：{unknown}")
    return dims


def merge_batch_files(paths, chapter: str, known_ids: set, batch_grouping: dict) -> dict:
    """合并多个批次 Phase A Markdown 文件，做批次完整性核对，返回合并后的维度字典。

    批次不完整（缺文件/维度数不符声明/维度集合与 batch_grouping 声明不符）一律
    raise ValueError，不静默拼接（方案 §C4 手段 2 纪律）。
    """
    seen_batches: dict = {}
    merged: dict = {}

    for p in paths:
        text = read_text(p)
        meta = parse_batch_metadata(text)
        if meta is None:
            raise ValueError(
                f"{p}: 缺少批次元数据 HTML 注释（首行须为 "
                f"'<!-- phase=A batch=N chapter=chXX dims=<count> -->'）"
            )
        if meta["phase"] != "A":
            raise ValueError(f"{p}: 元数据 phase={meta['phase']!r}，期望 'A'")
        if meta["chapter"] != chapter:
            raise ValueError(
                f"{p}: 元数据 chapter={meta['chapter']!r} 与 --chapter {chapter!r} 不一致"
            )

        batch_num = meta["batch"]
        if batch_num not in BATCH_KEY_BY_NUM:
            raise ValueError(f"{p}: 未知批次号 batch={batch_num}（应为 1/2/3）")
        if batch_num in seen_batches:
            raise ValueError(f"批次 {batch_num} 重复出现（文件 {seen_batches[batch_num]} 与 {p}）")

        dims = parse_markdown_dimensions(text)
        unknown = sorted(set(dims) - known_ids)
        if unknown:
            raise ValueError(f"{p}: 出现契约未声明的维度 id：{unknown}")

        if len(dims) != meta["dims"]:
            raise ValueError(
                f"{p}: 元数据声明 dims={meta['dims']}，实际解析出维度小节数={len(dims)}，批次不完整"
            )

        batch_key = BATCH_KEY_BY_NUM[batch_num]
        expected_ids = set(batch_grouping.get(batch_key, []))
        actual_ids = set(dims)
        if expected_ids and actual_ids != expected_ids:
            missing = sorted(expected_ids - actual_ids)
            extra = sorted(actual_ids - expected_ids)
            detail_parts = []
            if missing:
                detail_parts.append(f"缺失 {missing}")
            if extra:
                detail_parts.append(f"多余 {extra}")
            raise ValueError(
                f"{p}: 批次 {batch_num} 维度集合与 batch_grouping.{batch_key} 声明不符"
                f"（{'；'.join(detail_parts)}），批次不完整"
            )

        seen_batches[batch_num] = p
        merged.update(dims)

    missing_batches = sorted(set(BATCH_KEY_BY_NUM) - set(seen_batches))
    if missing_batches:
        raise ValueError(f"批次不完整，缺少批次号：{missing_batches}（须提供 batch1/2/3 三份文件）")

    return merged


def build_output(chapter: str, dims: dict) -> dict:
    """构造符合 schemas/auditor-phase-a.schema.json 顶层结构的 JSON。"""
    return {chapter: dims}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase A 确认式 Markdown -> JSON 落盘转换器（跨模型兼容性优化方案 §C4）"
    )
    parser.add_argument(
        "files", nargs="+",
        help="Phase A Markdown 输入文件；--merge 时按批次传入多个文件（batch1/2/3）",
    )
    parser.add_argument("--chapter", required=True, help="章节标识，如 ch01（JSON 顶层键）")
    parser.add_argument(
        "--merge", action="store_true",
        help="合并多个批次文件，校验各文件首行 HTML 注释元数据声明的批次完整性",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON（供 orchestrator 解析）")
    parser.add_argument("--out", default=None, help="将转换后的 JSON 写入指定路径")
    args = parser.parse_args()

    if not CHAPTER_ID_PATTERN.match(args.chapter):
        print(f"{FAIL} --chapter 格式不合法: {args.chapter}（须形如 ch01/ch012）", file=sys.stderr)
        sys.exit(2)

    for f in args.files:
        if not Path(f).exists():
            print(f"{FAIL} 文件不存在: {f}", file=sys.stderr)
            sys.exit(2)

    if not args.merge and len(args.files) != 1:
        print(
            f"{FAIL} 未指定 --merge 时只能传入单个文件，收到 {len(args.files)} 个",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        known_ids = load_known_dimension_ids()
    except Exception as e:
        print(f"{FAIL} 读取 auditor_contract.json 失败: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        if args.merge:
            batch_grouping = load_batch_grouping()
            dims = merge_batch_files(args.files, args.chapter, known_ids, batch_grouping)
        else:
            dims = parse_single_file(args.files[0], known_ids)
    except ValueError as e:
        print(f"{FAIL} {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"{FAIL} 解析异常: {e}", file=sys.stderr)
        sys.exit(2)

    output = build_output(args.chapter, dims)

    if sv is None:
        print(f"{FAIL} scripts/schema_validate.py 不可用，无法完成产出校验", file=sys.stderr)
        sys.exit(2)

    try:
        schema = sv.load_schema("auditor-phase-a")
        result = sv.validate_instance(output, schema)
    except Exception as e:
        print(f"{FAIL} schema 校验过程异常: {e}", file=sys.stderr)
        sys.exit(2)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps({
            "chapter": args.chapter,
            "output": output,
            "dimension_count": len(dims),
            "schema_valid": result["valid"],
            "errors": result["errors"],
            "out_path": str(args.out) if args.out else None,
        }, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        if result["valid"]:
            print(f"{OK} schema 校验通过（维度数={len(dims)}）", file=sys.stderr)
        else:
            print(f"{FAIL} schema 校验失败，共 {result['error_count']} 处错误：", file=sys.stderr)
            for e in result["errors"]:
                print(f"      - [{e['path']}] {e['message']}", file=sys.stderr)

    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
