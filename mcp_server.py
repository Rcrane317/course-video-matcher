#!/usr/bin/env python3
"""course-video-matcher MCP server.

把课件网课匹配流水线的四个脚本封装为标准 MCP 工具，
任何 MCP 客户端（Claude Desktop、Cursor、Cline、Windsurf 等）均可调用。

启动方式：
    pip install "mcp[cli]"        # 仅 MCP 模式需要，核心脚本零依赖
    python mcp_server.py          # stdio 传输，客户端自动拉起

客户端配置示例（Claude Desktop / Cursor / Cline 通用的 mcpServers 写法）：
    {
      "mcpServers": {
        "course-video-matcher": {
          "command": "python",
          "args": ["/绝对路径/to/course-video-matcher/mcp_server.py"]
        }
      }
    }

流水线对应关系（与 SKILL.md 的 Phase 一致）：
    Phase 0  unpack_materials   -> scripts/materials.py   解包课件、分课程、抽章节
    Phase 5  probe_links        -> scripts/probe.py       逐条核验 B站 链接是否在播
    Phase 6  align_and_rank     -> scripts/align.py       过滤、打分、排序
    Phase 6  validate_candidates-> scripts/align.py --validate  校验 candidates.json
    Phase 7  render_report      -> scripts/write_html.py  生成单文件 HTML 对照表

检索 B站 与撰写 candidates.json 属于 LLM 的语义工作，由客户端 agent
按 SKILL.md 的 Phase 1–4 完成，再通过 probe_links / align_and_rank 送回流水线。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

SKILL_DIR = Path(__file__).resolve().parent
SCRIPTS = SKILL_DIR / "scripts"

mcp = FastMCP("course-video-matcher")


def _run(args: list[str]) -> str:
    """运行脚本并返回 stdout（失败时附加 stderr 与退出码，不抛异常中断会话）。"""
    proc = subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(SKILL_DIR),
    )
    out = (proc.stdout or "").strip()
    if proc.stderr and proc.stderr.strip():
        out += "\n[stderr]\n" + proc.stderr.strip()
    if proc.returncode != 0:
        out += f"\n[exit_code] {proc.returncode}"
    return out or "(no output)"


def _load_json(path: str) -> str:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return json.dumps(data, ensure_ascii=False, indent=2)


@mcp.tool()
def unpack_materials(source: str, out_dir: str, no_unpack: bool = False,
                     max_files: int = 600) -> str:
    """Phase 0：解包课件压缩包并清点。

    按顶层目录分课程、抽取「第3章 / 3.2 / 第5讲 / L07」序号、按内容哈希去重，
    生成 <out_dir>/materials.json（含每份讲义的 slide_titles 与 text_head 线索）。

    Args:
        source: 压缩包（.zip/.7z/.rar/.tar.gz）或已解压文件夹的绝对路径
        out_dir: 输出工作目录（materials/ 与 materials.json 存放处）
        no_unpack: source 已是解压后的文件夹时置 true
        max_files: 最多处理的文件数上限
    """
    args = [str(SCRIPTS / "materials.py"), source, "--out", out_dir,
            "--max-files", str(max_files)]
    if no_unpack:
        args.append("--no-unpack")
    return _run(args)


@mcp.tool()
def validate_candidates(candidates_json: str, materials_json: str) -> str:
    """Phase 4：校验 agent 写好的 candidates.json。

    挑出：非 B站 链接、讲义对不上、series_id 悬空、分数越界。

    Args:
        candidates_json: candidates.json 文件路径
        materials_json: materials.json 文件路径
    """
    return _run([str(SCRIPTS / "align.py"), "--validate", candidates_json,
                 "--materials", materials_json])


@mcp.tool()
def probe_links(candidates_json: str, out_json: str,
                allow_unverified: bool = False) -> str:
    """Phase 5：逐条请求 B站 公开接口，核验每条链接「此刻还能不能看」。

    判定：alive 可看 / dead 已删除 / part_missing 分P不存在 /
    paid 付费 / mismatch 标题不符 / blocked 风控。返回 probe.json 全文。

    Args:
        candidates_json: candidates.json 文件路径
        out_json: probe.json 输出路径
        allow_unverified: blocked 的链接默认剔除；置 true 可保留但打「在播未核验」标
    """
    args = [str(SCRIPTS / "probe.py"), "--candidates", candidates_json,
            "--out", out_json]
    if allow_unverified:
        args.append("--allow-unverified")
    result = _run(args)
    try:
        return result + "\n\n[probe.json]\n" + _load_json(out_json)
    except Exception:
        return result


@mcp.tool()
def align_and_rank(materials_json: str, candidates_json: str, out_json: str,
                   probe_json: str = "", mode: str = "full",
                   allow_unverified: bool = False) -> str:
    """Phase 6：过滤、打分、按匹配度降序排序，输出 alignment.json 全文。

    五道门禁（B站/免费/完结/无广告/未删除）不受模式影响；
    mode 只改变关键词加分与体量权重。

    Args:
        materials_json: materials.json 路径
        candidates_json: candidates.json 路径
        out_json: alignment.json 输出路径
        probe_json: 可选，probe.json 路径；给了就按「此刻是否还能看」过滤
        mode: "full"（全程网课，默认）或 "crash"（突击网课）
        allow_unverified: 是否保留在播未核验的链接
    """
    args = [str(SCRIPTS / "align.py"), "--materials", materials_json,
            "--candidates", candidates_json, "--out", out_json, "--mode", mode]
    if probe_json:
        args += ["--probe", probe_json]
    if allow_unverified:
        args.append("--allow-unverified")
    result = _run(args)
    try:
        return result + "\n\n[alignment.json]\n" + _load_json(out_json)
    except Exception:
        return result


@mcp.tool()
def render_report(alignment_json: str, out_html: str,
                  title: str = "课件 ↔ 网课对照表") -> str:
    """Phase 7：把 alignment.json 渲染为单文件自包含 HTML 对照表。

    所有推荐项均为可点击 B站 链接，含「合集/片段」标签、
    匹配分、在播核验时间戳、过滤台账与覆盖率。

    Args:
        alignment_json: alignment.json 文件路径
        out_html: 输出 HTML 路径（主交付物）
        title: 页面标题
    """
    return _run([str(SCRIPTS / "write_html.py"), alignment_json,
                 "-o", out_html, "--title", title])


@mcp.tool()
def probe_single_url(url: str) -> str:
    """单测一条 B站 链接是否在播（调试用，不落盘）。"""
    return _run([str(SCRIPTS / "probe.py"), "--url", url])


if __name__ == "__main__":
    mcp.run()
