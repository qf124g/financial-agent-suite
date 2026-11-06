#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
私募基金问答 + 高德地图 双能力 Agent（MCP 可插拔演示）

本模块属于"金融场景多架构 Agent 套件"个人项目，演示 MCP 的核心价值：
同一个高德 MCP Server，不改一行业务代码，插进已有的反应式基金问答 Agent，
Agent 立刻从"只能答基金"升级为"基金问答 + 地图规划"双能力。

实现要点：
1. 本地工具（基金规则检索）直接 import 复用 fund_qa_langchain，零重复代码
2. 高德 MCP 工具通过 langchain-mcp-adapters 的 MultiServerMCPClient 动态加载
3. 两类工具合并进同一个 create_agent，模型按问题语义自动选择调用哪套工具
4. MCP stdio 子进程的 env 是"替换"而非"合并"，必须基于 os.environ 拷贝
"""

import sys
import asyncio
from pathlib import Path

from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

# 复用反应式基金问答模块的本地工具与配置（不重复造轮子）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fund_qa_langchain import (
    search_rules_by_keywords,
    search_rules_by_category,
    answer_question,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
)

# MCP Server 连接配置统一从注册表获取（集中管理，一处声明多处复用）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp_tools"))
from server_registry import get_server_config


async def create_pluggable_agent():
    """组装"本地工具 + MCP 远程工具"的双能力 Agent"""

    # ---- 本地工具：基金问答（原样复用）----
    local_tools = [search_rules_by_keywords, search_rules_by_category, answer_question]

    # ---- MCP 工具：从注册表取连接配置，动态插拔 ----
    # 要换/加 MCP 能力只需改这里的服务名，连接规格集中在 server_registry.py
    mcp_client = MultiServerMCPClient({"amap-maps": get_server_config("amap-maps")})
    mcp_tools = await mcp_client.get_tools()
    print(f"[MCP] 高德 Server 已接入，注入 {len(mcp_tools)} 个地图工具")

    llm = ChatOpenAI(
        model="qwen3.7-plus",
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
    )

    system_prompt = """你是一个双能力助手，同时具备两套工具：

一、私募基金问答（本地工具）：
1. search_rules_by_keywords: 通过关键词搜索基金规则
2. search_rules_by_category: 按类别查询规则（设立与募集、监管规定）
3. answer_question: 直接搜索并回答基金问题

二、地图与出行（高德 MCP 工具）：
- 地理编码、路线规划、周边搜索、天气查询、距离测量等，工具名以 maps_ 开头

使用规则：
1. 基金类问题优先使用本地基金工具；出行/地点/路线类问题使用高德地图工具
2. 基金知识库无信息时明确告知，不得编造
3. 回答要专业、简洁、准确"""

    # 关键一步：本地工具与 MCP 工具合并，统一交给 create_agent
    agent = create_agent(llm, local_tools + mcp_tools, system_prompt=system_prompt)
    return agent


async def main():
    agent = await create_pluggable_agent()

    print("\n=== 双能力 Agent（基金问答 + 高德地图，MCP 可插拔演示）===")
    print("可以问基金问题，也可以问地图/路线问题，输入'退出'结束\n")

    while True:
        user_input = input("请输入您的问题：")
        if user_input.lower() in ["退出", "exit", "quit"]:
            print("感谢使用，再见！")
            break

        response = await agent.ainvoke({"messages": [HumanMessage(content=user_input)]})
        for msg in reversed(response["messages"]):
            if isinstance(msg, AIMessage) and msg.content:
                print(f"回答: {msg.content}\n")
                break
        print("-" * 40)


if __name__ == "__main__":
    asyncio.run(main())
