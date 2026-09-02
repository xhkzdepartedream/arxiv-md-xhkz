# arxiv-md-xhkz

> **arXiv TeX → Markdown 转换器** · 社区维护版（fork）
>
> 上游：PyPI [`arxiv-md`](https://pypi.org/project/arxiv-md/) 0.1.0（作者 Mauro Sciancalepore，MIT）。
> 本仓库在原版基础上修复了一批**转写质量缺陷**（公式保真、参考文献、交叉引用、表格、脚注），
> 并新增了「公式附录」输出。模块导入名保持 `arxiv_md` 不变，与上游兼容。

`arxiv-to-md` 下载 arXiv 论文的 TeX 源码包，转成干净的 Markdown：

- 解析 `equation` / `align` / `gather` 等显示公式，**行内数学一律保留为 `$...$` LaTeX**（不做 Unicode 降级，`z_t` 不会被写成 `zₜ`）
- 图表交叉引用解析为数字编号（`Figure~\ref{fig:teaser}` → `Figure 1`）
- 表格渲染为 Markdown 管道表（无法表达的复杂表格保留 HTML）
- 输出 `document.md` + `conversion.json` 旁车文件 + `images/` 图片目录

## 与上游的差异

本 fork 的修复（全部实测验证）：

| 类别 | 上游问题 | 本版修复 |
|---|---|---|
| 公式 | 行内数学被降级为 Unicode 上下标（`cₜ`/`zₜ`），正文出现 `c_t` 与 `cₜ` 混用 | markdown 输出始终是 `$...$`，符号层面统一 |
| 公式 | `equation`/`align` 环境的 `\label` 丢失，无法引用编号 | `\label{eq:x}` 保留在公式块内 |
| 公式 | 公式无编号、无法核对 | **新增公式附录**：document.md 末尾按序附全部显示公式（编号 + 环境名 + `\label`） |
| 参考文献 | `.bib` 的 `@String` 宏定义泄漏成垃圾条目；ACM `.bbl` 跨行 `\bibitem` 解析为 0 条 | 只匹配真实条目类型；支持跨行 `\bibitem[...]%` 格式；剥离 `\bibfield`/`\bibinfo` 标记 |
| 交叉引用 | `teaserfigure` 未识别 → 整段落成代码块，`fig:teaser` 无法解析 | `teaserfigure` 按 figure 处理 |
| 交叉引用 | 一张表多个 `\label` 只保留第一个（`tab:scene` 悬空）；或错误编号为 `2b` | 表内全部 label 登记，**指向同一编号**（`Table 2`） |
| 表格 | 一律输出 HTML `<table>`，内联 style 体积膨胀数倍 | 简单表格输出**管道表**（保留 `**加粗**`），有行背景/跨格的复杂表保留 HTML |
| 表格 | 被注释掉的单元格行（`% & \textbf{Latency}...`）泄漏成空行 | 剔除 `%` 注释行 |
| 标题 | 图表标题不带编号（`*Table: ...*`，读者无法对应 "Table 3"） | 标题带编号：`*Table 3: ...*`、`![Figure 4: ...]` |
| 脚注 | 多作者只取第一个；`\authornote` 内容散落正文；`\authornotemark[1]` 泄漏孤立 `[1]` | 收集全部作者；作者注渲染为引用块；可选参数吸收 |

转写器**不修改原文内容**：原文自带的笔误（如公式左右项重复、`video gneration` 拼写）会被如实保留——这是特性，不是 bug。

## 安装

推荐 `uv`（也可用 `pip`）：

```console
# 直接从 GitHub 安装
uv tool install --from "git+https://github.com/xhkzdepartedream/arxiv-md-xhkz" arxiv-md-xhkz
# 或本地 checkout
uv tool install --from . arxiv-md-xhkz
# 图片栅格化（PDF→PNG）可选依赖
uv tool install --from . arxiv-md-xhkz --with "arxiv-md-xhkz[assets]"
```

装完三个命令进入 PATH：`arxiv-to-md`、`tex-to-md`、`tex-ast`。

## 快速开始

```console
# 按 arXiv ID 转换（下载源码 → TeX → Markdown）
arxiv-to-md 2506.04225 --outdir ./papers

# 搜索并转换 Top 3
arxiv-to-md --top-k 3 "world consistent video diffusion" --outdir ./papers

# 转换本地 .tex / 目录 / 源码压缩包
tex-to-md paper.tex --outdir ./out
```

每篇论文输出到 `<outdir>/<arxiv_id>/`：

```
2506.04225/
├── document.md        # 正文（含公式附录）
├── conversion.json    # 转换统计、警告、配置
└── images/            # 提取/栅格化的图片
```

## CLI 选项

| 选项 | 说明 |
|---|---|
| `--outdir DIR` | 必填。批量输出的父目录 |
| `--top-k N` | 搜索时返回并转换前 N 篇（默认 1） |
| `--keep-archive` | 保留下载的源码压缩包于 `<outdir>/.archives/` |
| `--keep-source` | 保留解压的源码树于 `<outdir>/<id>/source` |
| `--json` | stdout 输出机器可读 JSON 信封 |
| `--no-equation-appendix` | 不追加公式附录 |
| `--asset-mode rasterize\|copy\|skip` | PDF/JPEG 图资产处理方式（默认 rasterize，需 assets 依赖） |
| `--raster-dpi N` | PDF 栅格化 DPI（默认 120） |
| `--strict` | 有转换警告即失败 |

`tex-to-md` 额外接受 `--document-slug`、`--no-assets`。

## 公式附录

默认开启。`document.md` 末尾追加 `## Equation Appendix`，按原文顺序列出全部显示公式：

```
## Equation Appendix

> Display-math environments (equation/align/gather/...) kept verbatim from the
> TeX source in document order. ...

**1. \label{eq:double} — `equation`**

$$
\mathbf{z}'_{t,i} = f_D^i(...), ...
$$
```

编号与正文公式计数器一致，`\label` key 保留——正文里 "as shown in Eq. 3" 可以在这里直接核对原文。

## 开发

```console
git clone https://github.com/xhkzdepartedream/arxiv-md-xhkz
cd arxiv-md-xhkz
uv venv && uv pip install -e .
# 用本地代码跑转换（不装全局）：
uv run python -c "
from arxiv_md.tex import convert_path, ConvertOptions
res = convert_path('path/to/paper.tex', ConvertOptions(render_assets=False))
print(res.markdown[:500])
"
```

结构：`arxiv_md/tex/` 下是核心管线——`archive`（解压/探测 main.tex）→ `source`（`\input` 展开）→ `macros`/`macro_engine`（宏处理）→ `lexer`/`parser`（AST）→ `transform/`（块级转换、行内序列化、交叉引用）→ `rendering`（Markdown 渲染）。

## 许可

MIT。上游代码 © 2026 Mauro Sciancalepore；fork 修改 © 2026 xhkzdepartedream。
原项目未开源 Git 仓库，本 fork 基于 PyPI 发行版与作者本地开发版重建，如有版权疑问请联系上游作者（maurosciancalepore98@gmail.com）。
