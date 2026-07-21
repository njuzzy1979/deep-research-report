"""文本域处理阶段（阶段0-2）。

本包负责 Markdown 源文件的文本层处理：
  - 阶段0：二进制读取 + 行尾规范化（normalize.py）
  - 阶段1：规则表驱动文本清理（clean.py）——红队标记/密级过滤/HTML残留等
  - 阶段2：块级解析（parse.py）+ 行内解析（inline.py）

Token 类型定义集中存放于 tokens.py（纯数据，零逻辑）。
"""
