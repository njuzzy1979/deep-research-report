# -*- coding: utf-8 -*-
"""反硬编码静态扫描器（C-15 交付物，02-algorithms.md §F.3）。

对 md2docx 包做 AST 级静态扫描，落实 §F.2 判别口诀：

    "换一份完全不同主题的报告，该字符串是否仍必须出现在代码里？
     是 → 结构关键词（允许）；否 → 内容硬编码（违规）。"
    代码里能读出'这份报告写了什么' = 违规；
    只能读出'研究报告的语法长什么样 + 排成什么格式' = 合规。

本脚本实现 §F.3 的三项自动化手段中可静态化的部分：

  1. 中文字面量扫描（§F.3.1）：AST 遍历（优于 grep——可精确跳过 docstring/注释、
     可识别字面量所处的语法上下文），提取含 CJK 字符的字符串字面量，按上下文
     分类为"允许 / 疑似违规"。允许上下文严格对应 §F.2 允许清单：
       · docstring（模块/类/函数）与注释——非运行期数据；
       · __main__ 自检块内的字面量——测试脚手架，非产品逻辑；
       · Issue(message=/suggestion=…) 等"消息文案"——§F.2 明确允许；
       · 与结构量比较/成员判断的操作数（if x in FRONT_BACK_WORDS 之类）；
       · config.py 中带"出处"注释的白名单常量（§F.2 要求集中存放 + 逐条注明出处）。
     其余含 CJK 的字面量（尤其"能读出报告写了什么"的内容词）→ 报可疑。

  2. 结构违规模式扫描（§F.3.2 + §F.1 V4/V5/V6）：检测
       · 形如 {"1-1": (...)} 的"编号→内容"映射字典（V5，本次重设计的直接动因）；
       · 名为 *MAP/*CAPS/*MATCHERS 且含中文/编号键的容器（V4/V5/V6）；
       · 按序号索引取内容 caption = XXX[idx]（V6 形态，启发式提示人工复核）。

  3. M7 YAML schema 静态一致性（§F.3 附带）：校验 config.py 的 YAML 白名单
     （_BLOCK_ALLOWED_KEYS）三块齐备、behavior 白名单与 BehaviorFlags 字段同源，
     防止 schema 白名单与 dataclass 漂移导致未知键校验（M7）出现缺口。

退出码：发现任何违规 → 非零（1）；干净 → 0。CI 可直接消费。

用法：
    python -m md2docx.check_no_hardcode              # 扫描默认包目录
    python -m md2docx.check_no_hardcode --verbose    # 附允许项统计
    python -m md2docx.check_no_hardcode <dir>        # 指定扫描根
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_CJK_RE = re.compile(r"[一-鿿]")
_NUM_ID_KEY_RE = re.compile(r"^\d{1,3}-\d{1,3}$")  # 形如 "1-1" 的编号键（V5 信号）

# 正则元字符信号：字面量若含这些结构（且非纯自然语言），视为"正则模式"（§F.2 允许第3类）。
_REGEX_META_RE = re.compile(r"\\d|\\s|\\w|\[.*\]|\(\?:|\(\?<|\\\d|[\^$]|\{\d|\.\*|\.\+|\|")

# 明确的"内容硬编码"强信号：出现即高置信违规，不因上下文豁免。
#   · 图片/文件名字面量（§F.1 V2）：含图像扩展名
#   · 具体机构/产品名难以静态穷举，靠换样本金标准测试兜底，此处只抓文件名与编号内容对
_FILENAME_RE = re.compile(r"\.(png|jpg|jpeg|svg|gif|bmp|docx?|pdf)\b", re.IGNORECASE)

# 扫描默认根：本文件所在的 md2docx 包目录
_DEFAULT_ROOT = Path(__file__).resolve().parent

# 允许承载中文"消息文案"的关键字参数名（§F.2"消息文案"允许项）。
# Issue()/警告构造/报告拼接/argparse help 的文字提示均归此类。
_MESSAGE_KWARGS = frozenset({
    "message", "suggestion", "detail", "note", "desc", "hint",
    "help", "description", "metavar", "title",
})

# 方法名后缀：字面量作为这些调用的实参时视为"输出文案"（写入报告/日志/控制台/文档）。
# 例：lines.append("# 转换报告")、print(...)、logger.warning(...)、doc.add_paragraph("目录")
_OUTPUT_SINK_METHODS = frozenset({
    "append", "extend", "insert", "add", "write", "writelines",
    "print", "warning", "error", "info", "debug", "critical", "log",
    "format",
    # python-docx 文档写入方法：写入的是节标题/结构标签，属"结构文本输出"（非报告内容）
    "add_paragraph", "add_run", "add_heading", "add_page_break",
})

# issue-code 形态：形如 E-IMG-01 / W-HDR-03 / I-CLN-05 —— 同一调用里出现即视为
# "发 Issue/清理动作"语境，其内的中文字符串是诊断/动作标签（§F.2 消息文案）。
_ISSUE_CODE_RE = re.compile(r"^[EWIF]-[A-Z]{2,4}-\d{2}$")

# 变量名信号：中文字面量作为这类命名的赋值 RHS 时，视为"消息/标签文案"局部变量
# （随后被 append/f-string/add_run 消费）。名字读出的是"这是一段提示/标签"，非报告内容。
_MESSAGE_VAR_RE = re.compile(r"(text|hint|msg|message|label|meaning|line|lines|note|tip|title|prefix|suffix|desc|src|detail|parts|out|rows|summary|content)$", re.IGNORECASE)

# §F.2 明确允许的"格式常量：字体名"白名单（V3.0 §二/§三/§五）。这些字体名无论
# 出现在模块常量、默认参数值还是 OXML 设置调用中，都属排版格式常量，不是报告内容。
_ALLOWED_FONT_NAMES = frozenset({
    "宋体", "微软雅黑", "黑体", "仿宋", "楷体", "等线",
    "Times New Roman", "Consolas", "Arial", "Calibri",
})

# 被视为"结构量"的容器名——与之比较/成员判断的中文字面量属语法判定，允许
# （这些名字本身来自 config.py 白名单，其内容合规性由白名单出处注释保证）。
_STRUCTURAL_CONTAINERS = frozenset({
    "FRONT_BACK_WORDS", "SECRECY_WORDS_STRONG", "SECRECY_WORDS_WEAK",
    "SECRECY_FALSE_POSITIVE_PATTERNS",
})

# 允许的"纯结构标点/单字"字面量——即便含 CJK 也属语法结构（顿号、书名号等），
# 与具体报告内容无关。长度 <= 1 的中文串一律视为结构字符（如"第""章""图""表"）。
# 具名结构词（图/表/第/章/附录/摘要…）已集中在 config.py 常量，不在业务模块散落。


# ---------------------------------------------------------------------------
# 发现项
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    file: str
    line: int
    col: int
    code: str  # H1（内容硬编码）/ V4 / V5 / V6 / M7
    literal: str
    reason: str


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    allowed_count: int = 0  # 被判为允许的 CJK 字面量数（--verbose 统计用）
    scanned_files: int = 0


# ---------------------------------------------------------------------------
# AST 上下文分析
# ---------------------------------------------------------------------------


class _ModuleContext:
    """预扫描一个模块，标注 docstring 节点、__main__ 块行范围、白名单常量赋值行。"""

    def __init__(self, tree: ast.Module, module_name: str, source_lines: list[str]):
        self.module_name = module_name
        self.source_lines = source_lines
        self.docstring_ids: set[int] = set()
        self.main_block_lines: set[int] = set()
        self.provenance_const_lines: set[int] = set()
        self._mark_docstrings(tree)
        self._mark_main_block(tree)
        self._mark_provenance_constants(tree)

    def _mark_docstrings(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                body = getattr(node, "body", [])
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    self.docstring_ids.add(id(body[0].value))

    def _mark_main_block(self, tree: ast.Module) -> None:
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                t = node.test
                # if __name__ == "__main__":
                if (
                    isinstance(t, ast.Compare)
                    and isinstance(t.left, ast.Name)
                    and t.left.id == "__name__"
                ):
                    for child in ast.walk(node):
                        if hasattr(child, "lineno"):
                            self.main_block_lines.add(child.lineno)

    # 出处/来源标注信号：模块级"格式常量"（字体/字号/颜色/样式名）允许，
    # 但 §F.2 要求"须集中存放并注明出处"。此处认定"module 级常量赋值 + 行内或
    # 紧邻行含出处标注（V3.0/§/源自/出处/来源）"即满足出处要求，予以豁免。
    _PROV_RE = re.compile(r"V\d|§|出处|来源|源自|tech_full|interface-spec")

    def _mark_provenance_constants(self, tree: ast.Module) -> None:
        for node in tree.body:
            if isinstance(node, ast.Assign):
                ln = node.lineno
                # 行本身 + 其上一行注释 + 其下一行注释
                window_lines = []
                for i in (ln - 2, ln - 1, ln):
                    if 0 <= i < len(self.source_lines):
                        window_lines.append(self.source_lines[i])
                window = "\n".join(window_lines)
                if self._PROV_RE.search(window):
                    # 标注该赋值语句覆盖的所有行
                    end = getattr(node, "end_lineno", ln) or ln
                    for i in range(ln, end + 1):
                        self.provenance_const_lines.add(i)


def _walk_up(node: ast.AST, parent_map: dict, max_depth: int = 12):
    """自底向上迭代祖先节点（含起点的直接父级起）。"""
    cur = node
    for _ in range(max_depth):
        parent = parent_map.get(id(cur))
        if parent is None:
            return
        yield parent
        cur = parent


def _is_output_or_message_context(node: ast.Constant, parent_map: dict) -> bool:
    """字面量是否处于"消息文案 / 输出文本"语境（§F.2 允许）。

    覆盖：
      · Issue(message=/suggestion=…、argparse help=…) 等关键字实参；
      · lines.append("…")/print("…")/logger.warning("…") 等输出型调用实参；
      · f-string（JoinedStr）片段——运行期拼接的提示文字；
      · 隐式字符串拼接 / 括号内多段文案。
    向上穿过 JoinedStr/BinOp/Tuple/List 等中间容器追溯到"用途"节点。
    """
    for parent in _walk_up(node, parent_map):
        # message=/help=/suggestion= 等关键字实参
        if isinstance(parent, ast.keyword) and parent.arg in _MESSAGE_KWARGS:
            return True
        # f-string：字面量作为 f"…{x}…" 的静态片段 —— 运行期人读文案
        if isinstance(parent, ast.JoinedStr):
            return True
        # 输出型方法调用：xxx.append(...) / print(...) / logger.warning(...)
        if isinstance(parent, ast.Call):
            func = parent.func
            if isinstance(func, ast.Attribute) and func.attr in _OUTPUT_SINK_METHODS:
                return True
            if isinstance(func, ast.Name) and func.id in _OUTPUT_SINK_METHODS:
                return True
            # dict.get(key, "默认文案") 的默认实参 —— 回退标签文案
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and len(parent.args) >= 2
                and parent.args[1] is node
            ):
                return True
            # 发 Issue / 清理动作调用：同一 Call 的任一实参是 issue-code（E-IMG-01 等）
            # → 该调用是"报诊断/记动作"语境，其中文字符串为标签文案（§F.2 消息文案）
            for arg in list(parent.args) + [kw.value for kw in parent.keywords]:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and _ISSUE_CODE_RE.match(arg.value)
                ):
                    return True
        # int/enum → 文案 的映射字典值（如 {0: "成功", 1: "含 ERROR"}）—— 诊断词汇
        if isinstance(parent, ast.Dict):
            for k, v in zip(parent.keys, parent.values):
                if v is node and isinstance(k, ast.Constant) and isinstance(k.value, int):
                    return True
        # 中间容器：继续向上
        if isinstance(parent, (ast.JoinedStr, ast.FormattedValue, ast.BinOp,
                               ast.Tuple, ast.List, ast.Starred)):
            continue
    return False


def _is_registry_description(node: ast.Constant, parent_map: dict) -> bool:
    """字面量是否为"诊断/检查项登记表"中的描述文本（带出处的语法词汇）。

    形态：
      · IssueCodeInfo(Level.X, "描述", "出处") —— 第2位描述文本；
      · (1, "封面完整（…）") 之类 (int, str) 元组的字符串位 —— 门3检查项标签。
    这些是转换器自身的诊断词汇（§F.2"消息文案"，且 issues.py 逐条带 02§0.3 出处），
    不随被转换报告的题材变化，属允许。
    """
    parent = parent_map.get(id(node))
    # (int, "label") 元组：数字在前、字符串在后
    if isinstance(parent, ast.Tuple):
        elts = parent.elts
        if (
            len(elts) >= 2
            and isinstance(elts[0], ast.Constant)
            and isinstance(elts[0].value, int)
            and any(e is node for e in elts)
        ):
            return True
    # IssueCodeInfo(...) 或类似"信息登记"调用的字符串实参
    if isinstance(parent, ast.Call):
        func = parent.func
        fname = (
            func.attr if isinstance(func, ast.Attribute)
            else func.id if isinstance(func, ast.Name)
            else ""
        )
        if fname.endswith("Info") or fname.endswith("Spec") or fname.endswith("Meta"):
            return True
    return False


def _is_comparison_operand(node: ast.Constant, parent_map: dict) -> bool:
    """字面量是否用于与结构量比较/成员判断（if x in {...} / == '…'）。

    这类字面量表达的是"语法判定"，不是被写入产物的内容，属允许。
    仅当另一侧是已知结构容器名或该比较发生在纯判定语境时放行。
    """
    parent = parent_map.get(id(node))
    if isinstance(parent, ast.Compare):
        return True
    # 在集合/元组字面量里且该集合参与 in 比较（如 raw in {"图", "表"}）
    if isinstance(parent, (ast.Set, ast.Tuple, ast.List)):
        gp = parent_map.get(id(parent))
        if isinstance(gp, ast.Compare):
            return True
    return False


def _build_parent_map(tree: ast.AST) -> dict:
    parent_map: dict = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[id(child)] = node
    return parent_map


def _literal_is_allowed(
    node: ast.Constant,
    ctx: _ModuleContext,
    parent_map: dict,
    is_config: bool,
) -> tuple[bool, str]:
    """判定一个含 CJK 的字符串字面量是否属 §F.2 允许上下文。

    Returns (allowed, reason)。
    """
    value: str = node.value

    # ---- 强信号：文件名字面量（§F.1 V2）→ 违规，不因任何上下文豁免 ----
    #      （出现在 message 里描述"原始路径"属例外，见调用处已排除的 message 语境；
    #       此处只在"非消息语境"下判定——故先算消息语境再判文件名）
    in_message = _is_output_or_message_context(node, parent_map)

    # 1) docstring
    if id(node) in ctx.docstring_ids:
        return True, "docstring"

    # 2) __main__ 自检块（测试脚手架）
    if node.lineno in ctx.main_block_lines:
        return True, "__main__ 自检块"

    # 3) 纯结构单字（长度<=1，如"第""章""、"）——语法结构，非内容
    if len(value.strip()) <= 1:
        return True, "单字结构字符"

    # 3b) 模块级"格式常量"且带出处标注（字体名/样式名等，§F.2 格式常量类）
    if node.lineno in ctx.provenance_const_lines:
        return True, "带出处的格式常量"

    # 3c) §F.2 白名单字体名（格式常量，位置无关）
    if value.strip() in _ALLOWED_FONT_NAMES:
        return True, "白名单字体名（格式常量）"

    # 3d) 异常构造实参（raise XxxError("阶段名", …)）—— 诊断/阶段标签文案
    parent = parent_map.get(id(node))
    if isinstance(parent, ast.Call):
        fn = parent.func
        fname = (
            fn.id if isinstance(fn, ast.Name)
            else fn.attr if isinstance(fn, ast.Attribute)
            else ""
        )
        if fname.endswith("Error") or fname.endswith("Exception") or fname.startswith("_Stage"):
            return True, "异常/阶段诊断标签"

    # 4) 正则模式（§F.2 允许第3类：语法结构词 + 正则元字符 + 数字类）
    if _REGEX_META_RE.search(value):
        return True, "正则模式"

    # 5) 消息文案 / 输出文本（Issue message=/append/print/help= 等）
    if in_message:
        return True, "消息文案/输出文本"

    # 5b) 赋值给"消息/标签"型局部变量（hint_text/vd_line/detail 等），
    #     随后被输出消费——视为消息文案（§F.2）。
    for parent in _walk_up(node, parent_map):
        if isinstance(parent, ast.Assign):
            for tgt in parent.targets:
                if isinstance(tgt, ast.Name) and _MESSAGE_VAR_RE.search(tgt.id):
                    return True, "消息/标签型变量赋值"
            break
        if isinstance(parent, (ast.JoinedStr, ast.FormattedValue, ast.BinOp,
                               ast.Tuple, ast.List, ast.Starred, ast.Call)):
            continue
        break

    # 6) 诊断/检查项登记表描述（IssueCodeInfo / (int,label) 元组）
    if _is_registry_description(node, parent_map):
        return True, "诊断登记表描述（带出处）"

    # 7) 与结构量比较/成员判断的操作数
    if _is_comparison_operand(node, parent_map):
        return True, "比较/成员判断操作数"

    # 8) config.py 中的白名单常量赋值——集中存放且要求逐条出处注释（另由出处检查覆盖）
    if is_config:
        return True, "config.py 集中白名单常量"

    return False, ""


# ---------------------------------------------------------------------------
# 结构违规模式检测（§F.1 V4/V5/V6）
# ---------------------------------------------------------------------------


def _scan_structural_violations(
    tree: ast.Module, rel: str, result: ScanResult, ctx: "_ModuleContext"
) -> None:
    """检测编号→内容映射字典 / *MAP/*CAPS/*MATCHERS 容器 / 按序号取内容。

    __main__ 自检块内的容器（测试夹具，如 figure_registry={"1-1": fig1}）豁免。
    """
    for node in ast.walk(tree):
        # 跳过 __main__ 自检块（测试脚手架允许构造样例编号键）
        if getattr(node, "lineno", None) in ctx.main_block_lines:
            continue
        # ---- V5：形如 {"1-1": (...)} 的编号→内容映射 ----
        if isinstance(node, ast.Dict):
            num_keys = [
                k
                for k in node.keys
                if isinstance(k, ast.Constant)
                and isinstance(k.value, str)
                and _NUM_ID_KEY_RE.match(k.value)
            ]
            # 仅当"值含中文内容或多编号键"时才判违规——单个 {"1-1": var} 且值为
            # 变量引用（非内容字面量）不构成 FIGURE_MAP 式硬编码。
            if num_keys and (
                len(num_keys) >= 2
                or any(
                    isinstance(v, ast.Constant)
                    and isinstance(v.value, str)
                    and _CJK_RE.search(v.value)
                    for v in node.values
                )
            ):
                result.findings.append(
                    Finding(
                        file=rel,
                        line=node.lineno,
                        col=node.col_offset,
                        code="V5",
                        literal="{" + ", ".join(repr(k.value) for k in num_keys[:3]) + ", ...}",
                        reason="编号→内容映射字典（FIGURE_MAP/TBL_CAPS 类硬编码，§F.1 V5）",
                    )
                )

        # ---- V4/V5/V6：可疑命名的容器赋值 ----
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                name = tgt.id if isinstance(tgt, ast.Name) else None
                if name and re.search(r"(MAP|CAPS|MATCHERS)$", name):
                    val = node.value
                    # 容器内含中文字面量或编号键 → 命中
                    has_cjk = any(
                        isinstance(n, ast.Constant)
                        and isinstance(n.value, str)
                        and _CJK_RE.search(n.value)
                        for n in ast.walk(val)
                    )
                    if has_cjk:
                        result.findings.append(
                            Finding(
                                file=rel,
                                line=node.lineno,
                                col=node.col_offset,
                                code="V4",
                                literal=f"{name} = ...",
                                reason=f"可疑映射/匹配器容器 {name!r} 含中文内容（§F.1 V4/V5/V6，人工复核）",
                            )
                        )


# ---------------------------------------------------------------------------
# 单文件扫描
# ---------------------------------------------------------------------------


def scan_file(path: Path, root: Path, result: ScanResult) -> None:
    rel = str(path.relative_to(root.parent))
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - 语法错误直接报告
        result.findings.append(
            Finding(rel, exc.lineno or 0, 0, "SYN", "", f"语法错误无法解析：{exc}")
        )
        return

    result.scanned_files += 1
    ctx = _ModuleContext(tree, path.stem, src.splitlines())
    parent_map = _build_parent_map(tree)
    is_config = path.name == "config.py"

    # 中文字面量上下文分类
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
        ):
            # 强信号：非消息语境下的图片/文件名字面量（§F.1 V2）——即便无 CJK 也违规。
            # docstring / __main__ 自检块内的样例路径豁免（测试夹具）。
            val = node.value
            in_scaffold = (
                id(node) in ctx.docstring_ids or node.lineno in ctx.main_block_lines
            )
            if (
                _FILENAME_RE.search(val)
                and not in_scaffold
                and not _is_output_or_message_context(node, parent_map)
            ):
                # 排除 .docx/.md 等作为"扩展名替换"逻辑的通用后缀常量（无路径分隔/无具体名）
                if "/" in val or "\\" in val or _CJK_RE.search(val):
                    result.findings.append(
                        Finding(
                            file=rel, line=node.lineno, col=node.col_offset,
                            code="V2", literal=val[:60],
                            reason="疑似图表文件名字面量（§F.1 V2：文件名应来自文档解析，不得硬编码）",
                        )
                    )
                    continue

            if not _CJK_RE.search(val):
                continue
            allowed, _reason = _literal_is_allowed(node, ctx, parent_map, is_config)
            if allowed:
                result.allowed_count += 1
            else:
                result.findings.append(
                    Finding(
                        file=rel,
                        line=node.lineno,
                        col=node.col_offset,
                        code="H1",
                        literal=node.value[:60],
                        reason="疑似内容硬编码：非 docstring/消息文案/正则/判定操作数的中文字面量"
                        "（§F.2 判别口诀：能读出'报告写了什么'即违规）",
                    )
                )

    # 结构违规模式
    _scan_structural_violations(tree, rel, result, ctx)


# ---------------------------------------------------------------------------
# M7 YAML schema 静态一致性
# ---------------------------------------------------------------------------


def check_yaml_schema_consistency(result: ScanResult) -> None:
    """静态校验 config.py 的 YAML 白名单结构完备且与 BehaviorFlags 同源（M7）。"""
    try:
        # 延迟导入，避免扫描器对包内其它模块产生耦合
        if str(_DEFAULT_ROOT.parent) not in sys.path:
            sys.path.insert(0, str(_DEFAULT_ROOT.parent))
        from md2docx import config as cfg  # type: ignore
        from dataclasses import fields as _fields
    except Exception as exc:  # pragma: no cover
        result.findings.append(
            Finding("md2docx/config.py", 0, 0, "M7", "", f"无法导入 config 做 schema 校验：{exc}")
        )
        return

    # 三块齐备
    expected_blocks = {"metadata_defaults", "behavior", "report"}
    actual_blocks = set(getattr(cfg, "_BLOCK_ALLOWED_KEYS", {}).keys())
    if actual_blocks != expected_blocks:
        result.findings.append(
            Finding(
                "md2docx/config.py", 0, 0, "M7", "",
                f"YAML schema 块不完整：期望 {sorted(expected_blocks)}，实际 {sorted(actual_blocks)}",
            )
        )

    # behavior 白名单须与 BehaviorFlags 字段同源（防漂移）
    bf_fields = {f.name for f in _fields(cfg.BehaviorFlags)}
    behavior_allowed = set(cfg.BEHAVIOR_ALLOWED_KEYS)
    if behavior_allowed != bf_fields:
        missing = bf_fields - behavior_allowed
        extra = behavior_allowed - bf_fields
        result.findings.append(
            Finding(
                "md2docx/config.py", 0, 0, "M7", "",
                f"BEHAVIOR_ALLOWED_KEYS 与 BehaviorFlags 字段漂移："
                f"缺失={sorted(missing)} 多余={sorted(extra)}（M7 未知键校验将出现缺口）",
            )
        )

    # 顶层白名单一致
    if set(getattr(cfg, "TOP_LEVEL_ALLOWED_KEYS", set())) != expected_blocks:
        result.findings.append(
            Finding(
                "md2docx/config.py", 0, 0, "M7", "",
                f"TOP_LEVEL_ALLOWED_KEYS 与三块定义不一致",
            )
        )


# ---------------------------------------------------------------------------
# 出处注释检查（§F.3.1：白名单每项须带出处注释）
# ---------------------------------------------------------------------------


def check_whitelist_provenance(result: ScanResult) -> None:
    """校验 config.py §8 结构语义关键词白名单每个常量赋值近旁带"出处"注释。

    §F.3.1 要求"白名单每项须带出处注释，脚本校验注释存在性"。此处对 config.py
    §8 区块内的大写常量赋值，检查其行或紧邻行含"出处"/"来源"字样。
    """
    config_path = _DEFAULT_ROOT / "config.py"
    if not config_path.exists():
        return
    lines = config_path.read_text(encoding="utf-8").splitlines()

    # 定位 §8 结构语义关键词白名单区块
    start = end = None
    for i, ln in enumerate(lines):
        if "8. 结构语义关键词白名单" in ln:
            start = i
        elif start is not None and re.match(r"^# =====", ln) and i > start + 1:
            end = i
            break
    if start is None:
        return
    if end is None:
        end = len(lines)

    assign_re = re.compile(r"^([A-Z][A-Z0-9_]+)\s*=")
    for i in range(start, end):
        m = assign_re.match(lines[i])
        if not m:
            continue
        name = m.group(1)
        # 在赋值行前 2 行（前导注释惯例）至其后 3 行内查找"出处/来源"注释
        lo = max(start, i - 2)
        hi = min(i + 4, end)
        window = "\n".join(lines[lo:hi])
        if "出处" not in window and "来源" not in window:
            result.findings.append(
                Finding(
                    "md2docx/config.py", i + 1, 0, "PROV",
                    name,
                    f"白名单常量 {name!r} 缺少'出处'注释（§F.3.1 要求逐条注明出处）",
                )
            )


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def run_scan(root: Path, verbose: bool = False) -> ScanResult:
    result = ScanResult()
    py_files = sorted(
        p for p in root.rglob("*.py")
        if "__pycache__" not in p.parts
        and p.name != "check_no_hardcode.py"  # 不扫描自身
        and "tests" not in p.parts  # 测试夹具/断言含题材字面量，另由换样本金标准测试守护
    )
    for path in py_files:
        scan_file(path, root, result)

    check_yaml_schema_consistency(result)
    check_whitelist_provenance(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="md2docx 反硬编码静态扫描器（02-algorithms.md §F.3）"
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=str(_DEFAULT_ROOT),
        help="扫描根目录（默认：md2docx 包目录）",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="打印允许项统计")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[错误] 扫描根不存在：{root}", file=sys.stderr)
        return 2

    result = run_scan(root, verbose=args.verbose)

    print(f"反硬编码扫描：扫描 {result.scanned_files} 个 .py 文件")
    if args.verbose:
        print(f"  允许的 CJK 字面量（docstring/消息文案/判定操作数等）：{result.allowed_count}")

    if not result.findings:
        print("[通过] 未发现内容硬编码或结构违规。")
        return 0

    # 按文件分组打印
    print(f"\n[发现 {len(result.findings)} 项可疑/违规]：")
    by_code: dict[str, int] = {}
    for f in result.findings:
        by_code[f.code] = by_code.get(f.code, 0) + 1
    for f in result.findings:
        print(f"  {f.file}:{f.line}:{f.col} [{f.code}] {f.literal!r}")
        print(f"      → {f.reason}")
    print(f"\n分类统计：{by_code}")
    print("说明：H1=内容硬编码，V4/V5/V6=结构违规模式，M7=YAML schema 漂移，PROV=白名单缺出处注释")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
