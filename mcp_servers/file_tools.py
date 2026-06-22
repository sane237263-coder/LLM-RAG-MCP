# ============================================================
# mcp_servers/file_tools.py - 文件操作 MCP Server
# ============================================================
"""文件操作 MCP Server：读写删列搜，6 个工具。"""

import shutil
from pathlib import Path

from mcp.server.fastmcp import FastMCP

server = FastMCP("file-tools")


def _validate_path(path: str) -> Path:
    """安全路径校验：只允许在工作目录范围内操作。"""
    filepath = Path(path).resolve()
    workspace = Path.cwd().resolve()
    if not str(filepath).startswith(str(workspace)):
        raise ValueError(f"不允许操作工作目录外的文件: {filepath}")
    return filepath


@server.tool()
async def read_file(path: str) -> str:
    """读取本地文件内容。"""
    filepath = Path(path)
    if not filepath.exists():
        return f"错误: 文件不存在 — {filepath}"
    try:
        return filepath.read_text(encoding="utf-8")
    except Exception as e:
        return f"错误: 读取失败 — {e}"


@server.tool()
async def write_file(path: str, content: str) -> str:
    """将内容写入本地文件（路径白名单保护）。"""
    try:
        filepath = _validate_path(path)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(content, encoding="utf-8")
        return f"成功写入: {filepath} ({len(content)} 字符)"
    except ValueError as e:
        return f"错误: {e}"
    except Exception as e:
        return f"错误: 写入失败 — {e}"


@server.tool()
async def delete_file(path: str) -> str:
    """删除本地文件（路径白名单保护）。"""
    try:
        filepath = _validate_path(path)
        if not filepath.exists():
            return f"错误: 文件不存在 — {filepath}"
        filepath.unlink()
        return f"已删除: {filepath}"
    except ValueError as e:
        return f"错误: {e}"
    except Exception as e:
        return f"错误: 删除失败 — {e}"


@server.tool()
async def delete_directory(path: str) -> str:
    """递归删除目录及其所有内容（路径白名单保护）。"""
    try:
        filepath = _validate_path(path)
        if not filepath.exists():
            return f"错误: 目录不存在 — {filepath}"
        if not filepath.is_dir():
            return f"错误: 不是目录 — {filepath}"
        shutil.rmtree(filepath)
        return f"已删除目录: {filepath}"
    except ValueError as e:
        return f"错误: {e}"
    except Exception as e:
        return f"错误: 删除目录失败 — {e}"


@server.tool()
async def list_directory(path: str = ".") -> str:
    """列出目录中的文件和子目录（仅一层）。"""
    dirpath = Path(path)
    if not dirpath.exists():
        return f"错误: 目录不存在 — {dirpath}"
    try:
        items = []
        for item in sorted(dirpath.iterdir()):
            tag = "DIR" if item.is_dir() else "FILE"
            items.append(f"  [{tag}] {item.name}")
        return "\n".join(items) if items else "(空目录)"
    except Exception as e:
        return f"错误: 列出失败 — {e}"


@server.tool()
async def find_files(pattern: str) -> str:
    """递归搜索匹配的文件或目录，支持通配符（如 *.py、**/*.md）。"""
    try:
        workspace = Path.cwd()
        matches = sorted(workspace.glob(f"**/{pattern}"))
        if not matches:
            return f"未找到匹配的文件: {pattern}"
        items = []
        for m in matches:
            rel = m.relative_to(workspace)
            items.append(f"  [{'DIR' if m.is_dir() else 'FILE'}] {rel}")
        return f"找到 {len(items)} 个匹配:\n" + "\n".join(items)
    except Exception as e:
        return f"错误: 搜索失败 — {e}"


if __name__ == "__main__":
    server.run()
