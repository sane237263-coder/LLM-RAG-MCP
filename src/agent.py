# ============================================================
# src/agent.py - Agent 核心（Chat + MCP + RAG）
# ============================================================
import asyncio, json, re, shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from .config import AppConfig
from .llm import DeepSeekLLM
from .mcp_client import MCPClient
from .mcp_manager import MCPManager
from .tool_executor import ToolExecutor
from .rag import EmbeddingRetriever
from .types import ToolCall, LLMResponse
from .logger import (
    banner_chat, banner_response, banner_tools,
    banner_tool_use, banner_tool_result, banner_mcp_connect,
    banner_error, banner_rag,
    log_info, log_warn, log_debug,
)

class Agent:
    DEFAULT_SYSTEM_PROMPT = (
        "你可以调用工具来完成任务，包括读写文件、列目录、抓取网页等。"
        "当需要使用工具时，请严格按 function calling 格式返回。"
        "用中文礼貌地回答用户的问题。"
    )
    _MODEL_IDENTITY = {
        "deepseek-chat": "我是 DeepSeek，由深度求索公司开发的 AI 智能助手。",
        "deepseek-reasoner": "我是 DeepSeek-R1，由深度求索公司开发的推理模型。",
        "gpt-4o": "我是 GPT-4o，由 OpenAI 开发的 AI 助手。",
        "gpt-4": "我是 GPT-4，由 OpenAI 开发的 AI 助手。",
        "claude": "我是 Claude，由 Anthropic 开发的 AI 助手。",
        "qwen": "我是 Qwen（通义千问），由阿里云开发的 AI 助手。",
    }

    def __init__(self, config: AppConfig):
        self.model = config.llm.model
        self.system_prompt = self.DEFAULT_SYSTEM_PROMPT
        self._config = config
        self._mcp_clients: list[MCPClient] = []
        self._mcp_manager = MCPManager(config.mcp_servers)
        self._tool_executor = ToolExecutor(self._mcp_manager)
        self._retriever: EmbeddingRetriever | None = None
        self._rag_data_url = ""
        self._loaded_docs: set[str] = set()          # 已加载的文档，防重复
        self._loaded_sources: set[str] = set()       # 已加载的 RAG 源，防重复
        if config.embedding.api_key:
            self._retriever = EmbeddingRetriever(
                api_key=config.embedding.api_key,
                base_url=config.embedding.base_url,
                model=config.embedding.model,
            )
        self.llm: DeepSeekLLM | None = None

    # ================================================================
    # Public
    # ================================================================

    async def init(self):
        self.llm = DeepSeekLLM(config=self._config.llm, system_prompt=self._build_system_prompt())
        log_info(f"LLM init: model={self.model}")
        await self._mcp_manager.connect_all()
        self._mcp_clients = list(self._mcp_manager.clients)
        if self._config.embedding.data_url:
            await self.reload_rag(self._config.embedding.data_url)
        memory_path = self._resolve_memory_path()
        if memory_path.exists():
            try:
                state = json.loads(memory_path.read_text("utf-8"))
                self.llm.load_state(state)
                log_info(f"Memory restored: {memory_path} ({self.llm.message_count} msgs)")
            except Exception as e:
                log_info(f"Memory restore failed: {e}")
                self.llm.reset_conversation()
        else:
            self.llm.reset_conversation()

        # 自动加载本地数据
        if Path("data/employees.json").exists():
            await self.reload_rag("data/employees.json")
        if Path("data/docs").is_dir():
            await self.load_docs("data/docs")

        log_info("Agent init done")

    async def close(self):
        log_info("Agent closing...")
        if self.llm:
            memory_path = self._resolve_memory_path()
            try:
                state = self.llm.save_state()
                memory_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                log_info(f"Memory saved: {memory_path} ({self.llm.message_count} msgs)")
            except Exception as e:
                log_info(f"Memory save failed: {e}")
        await self._mcp_manager.disconnect_all()
        self._mcp_clients.clear()
        log_info("Agent closed")

    async def invoke(self, prompt: str) -> LLMResponse:
        if self.llm is None:
            raise RuntimeError("Agent not initialized")

        augmented_prompt = await self._augment_prompt(prompt)

        banner_chat()
        log_info(f"User: {prompt}")

        tools = self._mcp_manager.get_tools_for_llm() if self._mcp_manager.is_connected else None
        last_response = None

        for round_num in range(1, self._config.system.max_tool_rounds + 1):
            raw_response = await self.llm.chat(
                user_message=augmented_prompt if round_num == 1 else "",
                tools=tools,
            )
            last_response = LLMResponse(
                content=raw_response.get("content", ""),
                tool_calls=[
                    ToolCall(id=tc["id"], name=tc["function"]["name"], raw_arguments=tc["function"]["arguments"])
                    for tc in (raw_response.get("tool_calls") or [])
                ],
                finish_reason=raw_response.get("finish_reason", "stop"),
            )
            if last_response.content:
                banner_response()
            if not last_response.tool_calls:
                return last_response
            log_info(f"Tool round {round_num}: {len(last_response.tool_calls)} calls")
            results = await self._tool_executor.execute_tool_calls([
                {"id": tc.id, "function": {"name": tc.name, "arguments": tc.raw_arguments}}
                for tc in last_response.tool_calls
            ])
            for result in results:
                self.llm.add_tool_result(result["tool_call_id"], result["tool_name"], result["result"])
            augmented_prompt = ""
        log_warn(f"Max tool rounds ({self._config.system.max_tool_rounds})")
        return last_response or LLMResponse(content="(max rounds)", finish_reason="stop")

    async def reload_rag(self, url: str) -> str:
        if not self._retriever:
            return "RAG disabled (no embedding.api_key)"

        # 去重：已加载过的源跳过
        source_key = str(Path(url).resolve()) if not url.startswith(("http://","https://")) else url
        if source_key in self._loaded_sources:
            return f"RAG skipped (already loaded): {url}"

        self._rag_data_url = url
        log_info(f"RAG downloading: {url}")

        # 支持本地文件路径和 HTTP URL
        if url.startswith("http://") or url.startswith("https://"):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    items: list[dict] = resp.json()
            except Exception as e:
                msg = f"RAG download failed: {e}"
                log_warn(msg)
                return msg
        else:
            # 本地文件路径
            local_path = Path(url).resolve()
            if not local_path.exists():
                msg = f"RAG file not found: {local_path}"
                log_warn(msg)
                return msg
            try:
                items: list[dict] = json.loads(local_path.read_text(encoding="utf-8"))
            except Exception as e:
                msg = f"RAG local file read failed: {e}"
                log_warn(msg)
                return msg
        if not isinstance(items, list):
            return f"Expected JSON array, got {type(items).__name__}"
        for item in items:
            self._retriever.embed_document(json.dumps(item, ensure_ascii=False))
        self._loaded_sources.add(source_key)
        log_info(f"RAG index appended: +{len(items)}, total {self._retriever.vector_store.size}")
        return f"RAG loaded: {len(items)}, total index {self._retriever.vector_store.size}"

    async def load_docs(self, directory: str) -> str:
        """扫描目录中的 .md 文件，直接喂纯文本给向量库。不走 JSON。

        用法: /load_docs data/docs
        """
        if not self._retriever:
            return "RAG disabled (no embedding.api_key)"
        doc_dir = Path(directory)
        if not doc_dir.is_dir():
            return f"目录不存在: {doc_dir}"
        md_files = sorted(doc_dir.glob("*.md"))
        if not md_files:
            return f"目录中没有 .md 文件: {doc_dir}"
        count = 0
        skipped = 0
        for md_file in md_files:
            key = str(md_file.resolve())
            if key in self._loaded_docs:
                skipped += 1
                continue
            content = md_file.read_text(encoding="utf-8").strip()
            if not content:
                continue
            self._retriever.embed_document(content)
            self._loaded_docs.add(key)
            count += 1
        msg = f"Docs loaded: +{count}"
        if skipped:
            msg += f" (skipped {skipped})"
        msg += f" -> total index {self._retriever.vector_store.size}"
        log_info(f"RAG {msg}")
        return msg

    # ================================================================
    # Convenience
    # ================================================================

    def get_tools_summary(self):
        return [{"name": t["name"], "description": t.get("description", ""), "server": t.get("server_name", "?")}
                for t in self._mcp_manager.tools]

    def reset_conversation(self, clear_rag: bool = True):
        if self.llm:
            self.llm.reset_conversation()
            try:
                self._resolve_memory_path().unlink(missing_ok=True)
            except Exception:
                pass
        if clear_rag:
            if self._retriever:
                self._retriever.vector_store.clear()
                self._rag_data_url = ""
                self._loaded_docs.clear()
                self._loaded_sources.clear()

    # ================================================================
    # RAG internals
    # ================================================================

    async def _augment_prompt(self, prompt: str) -> str:
        if not self._retriever or self._retriever.vector_store.size == 0:
            return prompt
        banner_rag()
        top_k = self._config.embedding.top_k
        try:
            results = self._retriever.retrieve(prompt, top_k=top_k)
        except Exception as e:
            log_warn(f"RAG retrieve failed: {e}")
            return prompt
        if not results:
            log_info("RAG: no results")
            return prompt

        # --- 相似度阈值过滤：最高分太低说明库中没有相关内容 ---
        best_score = results[0]["score"]
        if best_score < 0.4:
            log_info(f"RAG: best score {best_score:.4f} < 0.4, skip context injection")
            return prompt

        # --- Print all top_k detail to terminal ---
        sep = "=" * 50
        print(f"\n  {sep}")
        print(f"  RAG: top_{top_k} results ({len(results)} found):")
        for i, r in enumerate(results):
            print(f"  --- #{i+1} score={r['score']:.4f} ---")
            # 通用显示：直接 dump JSON，不假设任何字段结构
            doc_str = r["document"]
            if len(doc_str) > 500:
                doc_str = doc_str[:500] + "..."
            print(f"  {doc_str}")
        print(f"  {sep}\n")

        # --- Build augmented prompt ---
        # 通用方案：直接传原始 JSON 文本给 LLM，不做字段拆解
        ctx = ["## RAG context (top_k={})".format(len(results))]
        for i, r in enumerate(results):
            doc_text = r["document"]
            if len(doc_text) > 800:
                doc_text = doc_text[:800] + "..."
            ctx.append(f"### {i+1}. score={r['score']:.4f}")
            ctx.append(doc_text)
        context = "\n".join(ctx)
        augmented = f"{prompt}\n\n{context}\n\nReply using the above RAG context."
        log_info(f"RAG context injected: {len(context)} chars")
        return augmented

    # ================================================================
    # Internal
    # ================================================================

    def _resolve_memory_path(self) -> Path:
        return Path(self._config.system.memory_file).resolve()

    def _build_system_prompt(self) -> str:
        identity = self._MODEL_IDENTITY.get(self.model, f"我是 {self.model} AI 智能助手。")
        return f"{identity}\n\n{self.system_prompt}"
