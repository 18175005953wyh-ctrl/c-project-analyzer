# C Project Analyzer

一个使用 Python 标准库编写的命令行工具，用于递归扫描 C 项目，统计代码、注释和空行，并生成 JSON 与 Markdown 报告。

## 项目背景

学习 C 语言之后，可以用 Python 编写一个小工具来观察项目由多少文件和多少行代码组成。本项目适合作为文件处理、状态机和自动化测试的入门练习，也可以配合本仓库的 CampusTreeManager 项目演示。统计结果用于了解项目结构，不表示代码质量或开发效率。

本工具位于当前仓库的 `c-project-analyzer/` 子目录，原来的 CampusTreeManager 项目仍保留在仓库根目录。下面的命令除特别说明外，均在 **`c-project-analyzer` 目录内**运行。

## 主要功能

- 递归查找 `.c` 和 `.h` 文件，扩展名不区分大小写。
- 汇总源文件数、头文件数、总行数、代码行数、注释行数、空行数。
- 统计 `TODO`、`FIXME`，计算代码和注释占总行数的百分比。
- 显示每个文件的数据，以及总行数最多的前 N 个文件。
- 排除构建目录、Git 目录、虚拟环境、缓存目录和本次报告输出目录。
- 在终端输出摘要，在输出目录创建 `report.json` 和 `report.md`。
- 对无效参数、读取失败、UTF-8 解码失败及报告写入失败给出简短提示。

## 目录结构与模块职责

```text
c-project-analyzer/
├── src/
│   ├── analyzer.py             # 命令行参数和流程协调
│   └── project_analyzer/
│       ├── __init__.py
│       ├── scanner.py          # 查找文件、排除目录、UTF-8 读取
│       ├── counter.py          # 行分类和标记统计
│       └── reporter.py         # 汇总、排行榜、三种输出形式
├── tests/
│   ├── sample_project/
│   │   ├── main.c
│   │   ├── example.c
│   │   └── example.h
│   └── test_analyzer.py
├── output/
│   └── .gitkeep
├── screenshots/
│   └── .gitkeep
├── .gitignore
├── LICENSE
└── README.md
```

## 环境与技术

需要 **Python 3.10 或更高版本**。运行分析器不需要 C 编译器，不需要安装任何第三方依赖，也无需执行 `pip install`。

主要使用 `argparse` 解析参数、`pathlib`/`os.walk` 处理目录、`re` 统计标记、`json` 序列化报告、`datetime` 记录 UTC 时间、`unittest` 进行测试。核心注释识别使用逐字符状态机，以便理解跨行块注释的处理过程。

## Windows 运行方法

先安装 Python 3.10+，并确保 `python` 命令可用。在文件资源管理器中进入本工具目录，在地址栏输入 `powershell` 并按回车，然后执行：

```powershell
python --version
python src/analyzer.py tests/sample_project
```

如果终端当前在 CampusTreeManager 仓库根目录，先执行：

```powershell
cd c-project-analyzer
```

如果电脑使用 Python Launcher，可将命令中的 `python` 替换为 `py -3`。若提示 Python 版本过低，应换用已安装的 3.10+ 解释器。

## Linux/macOS 运行方法

从仓库根目录开始：

```sh
cd c-project-analyzer
python3 --version
python3 src/analyzer.py tests/sample_project
```

其他示例中的 `python` 在这些平台可以替换成 `python3`。代码使用跨平台标准库；本次实际运行环境为 Windows，未声称已经在 Linux/macOS 主机执行验证。

## 参数与示例

```text
python src/analyzer.py <目标目录> [--output 输出目录] [--top 数量]
```

| 参数 | 含义 | 默认值 |
| --- | --- | --- |
| 目标目录 | 递归扫描的 C 项目目录，必填 | 无 |
| `--output` | JSON 和 Markdown 输出目录，不存在会创建 | 工具自身目录下的 `output/` |
| `--top` | 按总行数列出的文件数，必须为正整数 | 3 |
| `--help` | 查看参数帮助 | 无 |

```sh
python src/analyzer.py tests/sample_project
python src/analyzer.py tests/sample_project --output output
python src/analyzer.py tests/sample_project --top 5
python src/analyzer.py tests/sample_project --top 2
python src/analyzer.py ../src --output output/campus
python src/analyzer.py --help
```

`../src` 是本仓库原有的 CampusTreeManager 源码目录。路径含空格时请加引号，例如 `python src/analyzer.py "../My C Project"`。

目标路径和显式传入的 `--output` 相对于终端工作目录解析；未指定 `--output` 时始终写入本工具的 `output/`，不会因为从其他目录启动而改变。输出目录不允许等于目标目录，也不能是目标目录的祖先；可以位于目标目录内，其内容会被扫描器跳过。

## 实际样例输出

以下为运行 `python src/analyzer.py tests/sample_project` 得到的终端内容：

```text
===== C Project Analyzer =====
Target: sample_project
Files analyzed: 3 (C: 2, H: 1)
Files discovered: 3; skipped: 0
Total lines: 25
Code lines: 15 (60.00%)
Comment lines: 6 (24.00%)
Blank lines: 4
TODO: 2; FIXME: 1
Top 3 files (by total lines):
  1. example.c: 10 lines
  2. main.c: 8 lines
  3. example.h: 7 lines
Reports written: report.json and report.md
```

这里 `25 = 15 + 6 + 4`。更改 `--top` 只改变排行榜长度，不改变汇总结果。

## JSON 与 Markdown 报告

默认输出为 `output/report.json` 和 `output/report.md`，可用文本编辑器打开。Markdown 适合阅读和展示，JSON 适合后续编程处理。

JSON 的顶层字段如下：

| 字段 | 内容 |
| --- | --- |
| `target` | 目标目录名称，不保存本机绝对路径 |
| `analyzed_at` | 带 UTC 时区的分析时间 |
| `complete` | 是否完整；遇到读取或解码警告时为 `false` |
| `discovered_file_count` | 成功遍历到的候选文件数，含无法读取的文件 |
| `skipped_file_count` | 因读取或编码错误跳过的文件数 |
| `summary` | 文件数、六类计数，以及两个百分比 |
| `files` | 每个成功读取文件的相对路径、类型及六类计数 |
| `top_files` / `top_requested` | 排行榜及用户要求的数量 |
| `warnings` | 相对路径和简短错误原因 |
| `rules` | 本版本的统计规则 |

`summary` 包含 `file_count`、`c_file_count`、`h_file_count`、`total_lines`、`code_lines`、`comment_lines`、`blank_lines`、`todo_count`、`fixme_count`、`code_ratio` 和 `comment_ratio`。比例单位为百分比，例如 `60.0` 表示 60%，不是 0.6。

Markdown 包含标题、目标、时间、汇总表、排行榜、逐文件表、警告和规则。表格中的特殊路径字符会被转义。报告只记录目标目录名以及相对文件路径，避免包含无关的本地目录信息。

每次运行会替换这两个同名报告；先写临时文件，再分别替换目标文件。单个文件不会以写入一半的内容覆盖旧报告，但两个文件不是一个事务：第二次替换失败时，两份报告可能来自不同运行，此时退出码为 1。生成报告和测试临时文件均被 `.gitignore` 排除。

## 统计规则

1. 统计物理行，兼容 LF、CRLF 和 CR。最后一个换行符不会额外增加一行；空文件为零行。
2. 只有空白字符的行算空行，包括块注释内部的空白行。
3. 没有代码、只有注释的非空行算注释行；支持 `//`、`/* ... */` 和跨行块注释。
4. 同时出现代码和注释的行算代码行，例如 `int count = 0; // initialize count`，以及 `/* note */ int count;`。
5. 普通字符串和字符字面量中的注释符号不会开始注释；支持引号转义和简单的字符串反斜杠续行。
6. `TODO`、`FIXME` 在全文中按区分大小写的完整单词统计，包含代码、字符串及注释。`todo`、`TODO_count` 不匹配，一行出现两次 `TODO` 会计数两次。
7. 代码和注释占比均以总行数为分母，保留两位小数；总行数为零时占比为零。
8. 排行榜按总行数降序，同样行数时按相对路径升序，保证结果稳定。
9. 汇总只包含成功读取的文件，始终满足 `总行数 = 代码行数 + 注释行数 + 空行数`。

递归遍历中按目录名忽略大小写，跳过：

```text
.git  .vs  .vscode  .idea  build  dist  out  __pycache__  venv  .venv
```

还会跳过本次指定的输出目录、符号链接文件和目录；Python 3.12+ 会额外明确跳过 Windows junction。被排除的目录不会算作读取警告。只有 `.c`、`.h` 文件会被分析，JSON 和 Markdown 本身不会进入统计。

## 错误处理与退出码

| 情况 | 处理 | 退出码 |
| --- | --- | --- |
| 正常分析 | 输出终端摘要和两份报告 | 0 |
| 空目录或没有 C/H 文件 | 输出零值报告和提示 | 0 |
| 部分文件读取失败、编码异常或子目录不可读 | 跳过并记录警告，`complete=false` | 0 |
| 全部候选文件都无法读取 | 输出零值、不完整报告及警告 | 0 |
| 目标不存在、不是目录，或输出路径无效 | 输出 `Error:`，不打印异常堆栈 | 1 |
| 创建或写入报告失败 | 输出简短错误提示 | 1 |
| `--top` 非正整数、缺少参数等 | argparse 显示使用帮助和错误 | 2 |

输入文件采用 UTF-8，允许 UTF-8 BOM。不使用替换字符掩盖解码失败。读取目录失败时，尚未访问到的文件数无法确定，因此 `discovered_file_count` 不是对不可访问目录中实际文件数的估计。

## 自动化测试

在本工具目录运行：

```sh
python -m unittest discover -s tests -v
```

测试包含样例的精确计数、所有排除目录、相加不变量、TODO/FIXME 规则、混合注释、转义引号、空目录、错误路径、UTF-8 BOM、错误编码、读取权限失败、两类报告写入失败、排行榜排序和子进程命令行调用。权限错误部分使用标准库 `unittest.mock` 模拟，便于在不同操作系统复现。

测试数据临时生成于 `output/test-*`，每项结束时自动清理；不改动 `tests/sample_project` 中的样例。创建符号链接需要宿主权限，不具备权限时该项明确显示 `skipped`。

2026-09-17 在 Windows、Python 3.12.14 中实际执行了 29 项测试：**28 项通过，1 项因系统不允许创建符号链接而跳过，零失败**。同日还实际执行了默认样例、`--top 2`、帮助命令、不存在的目录和空目录；退出码分别符合上表。没有在未运行的 Python 版本或操作系统上声称通过测试。

## 当前限制

- 这是文本统计工具，不是 C 编译器或完整语法解析器，不检查代码能否编译。
- 不展开宏，不排除 `#if 0` 中的文本；不完整实现 C 翻译阶段的反斜杠拼接、三字符组等规则。续行的 `//` 注释和由续行拼成的注释界定符可能误判。
- 非法或未闭合的 C 字符串按当前行恢复，未闭合块注释持续到文件末尾。
- 仅支持 UTF-8；GBK 等编码文件会被明确跳过。
- 每次将一个文件读入内存，不适合极大的单个源文件；扫描期间没有文件系统快照或并发修改保护。
- 目标只保留目录名称，同名的不同目录需要由用户区分；文件路径在报告中相对于扫描目标。
- 不跟随符号链接。Windows junction 的显式识别依赖 Python 3.12+；使用 3.10/3.11 时建议避免扫描含 junction 的目录。
- 没有图形界面、复杂度分析、函数识别或历史变化比较。

## 后续改进方向

可以增加自定义排除规则、流式读取大文件、报告前后对比，以及更完整的 C 续行识别。在保留简单命令行入口的前提下，再考虑函数统计或图形化展示。

## 项目中练习到的能力

- 将命令行、遍历、计数和报告拆成职责清楚的模块。
- 用字典和列表组织数据，用排序实现排行榜。
- 用状态变量跟踪跨行块注释，理解单纯正则匹配的局限。
- 处理编码、相对路径、异常和退出码。
- 生成可供程序读取的 JSON 和可供人阅读的 Markdown。
- 用 unittest 检查精确结果与错误路径，并如实记录跳过的测试。

## 截图与许可证

`screenshots/.gitkeep` 保留截图目录，目前没有截图。可以运行样例后保存终端截图，以及 Markdown 报告的预览截图，再补充到此文档。

本子项目使用 [MIT License](LICENSE)。该许可证适用于本子目录中的 C Project Analyzer 文件，不改变仓库其他项目的许可状态。
