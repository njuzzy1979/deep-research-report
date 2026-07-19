"""
md2docx - Markdown → Word (.docx) 研究报告格式转换引擎

将符合约定的 Markdown 研究报告转换为严格遵循《研究报告格式规范 V3.0》的 Word 文档。

核心管道: Preprocessor → Parser → IR Builder → Renderer → Postprocessor
"""

__version__ = "2.0.0"

from .preprocessor import preprocess
from .parser import parse_markdown
from .config import Config, load_config
from .ir import DocumentIR, build_ir
