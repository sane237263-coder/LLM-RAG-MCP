# ============================================================
# mcp_servers/web_tools.py - 网页抓取 MCP Server
# ============================================================
"""网页抓取 MCP Server：抓取网页内容并保存摘要。"""

import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx
from mcp.server.fastmcp import FastMCP

server = FastMCP("web-tools")


def _html_to_text(html: str) -> str:
    """简单 HTML → 纯文本转换。"""
    text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', text).strip()


@server.tool()
async def web_fetch_summary(url: str, max_length: int = 2000) -> str:
    """抓取网页内容，生成摘要并保存为 Markdown 文件到 abstract/ 目录。

    Args:
        url: 网页 URL
        max_length: 摘要最大字符数（默认 2000）
    """
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            response.raise_for_status()
            html = response.text
    except Exception as e:
        return f"错误: 网页抓取失败 — {e}"

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    page_title = title_match.group(1).strip() if title_match else None

    text = _html_to_text(html)
    summary = text[:max_length]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if page_title:
        safe_title = re.sub(r"[\\/:*?\"<>|]", "_", page_title)[:60]
        filename = f"{safe_title}.md"
    else:
        domain = urlparse(url).netloc.replace(":", "_").replace(".", "_")
        filename = f"{domain}.md"

    out_dir = Path("abstract")
    out_dir.mkdir(parents=True, exist_ok=True)
    filepath = out_dir / filename

    md_content = f"""# {page_title or url}

> 来源: [{url}]({url})
> 抓取时间: {timestamp}
> 原始长度: {len(text)} 字符

---

{summary}
"""
    filepath.write_text(md_content, encoding="utf-8")
    save_msg = f"已保存到: {filepath}"

    return f"来源: {url}\n标题: {page_title or '(无)'}\n原始长度: {len(text)} 字符\n{save_msg}\n\n内容摘要:\n\n{summary}"


if __name__ == "__main__":
    server.run()
