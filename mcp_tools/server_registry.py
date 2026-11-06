#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""MCP Server 连接注册表

集中声明本项目用到的所有 MCP Server 连接配置（插头规格），
各 Agent 客户端统一从这里取配置，避免每个文件重复抄写 command/args/env。

对标 Claude Desktop / Cursor 的 mcp.json 集中管理思路：
Server 一次声明，任意 Agent 一行接入。

注意：MCP stdio 子进程的 env 是"替换"而非"合并"，
必须基于 os.environ 拷贝后再注入业务变量，否则 PATH 丢失。
"""

import os


def _base_env() -> dict:
    """拷贝父进程完整环境，作为各 Server 子进程 env 的基底"""
    return dict(os.environ)


def get_server_config(name: str) -> dict:
    """按名称获取 MCP Server 的 stdio 连接配置

    Args:
        name: Server 名称，当前支持 "amap-maps" / "txt-counter"

    Returns:
        符合 MCP stdio 连接规范的配置字典（transport/command/args/env）
    """
    registry = {
        # 高德官方地图 Server（Node 包，需 Node 20+ 与 AMAP_API_KEY）
        "amap-maps": {
            "transport": "stdio",
            "command": "npx",
            "args": ["-y", "@amap/amap-maps-mcp-server"],
            "env": {
                **_base_env(),
                "AMAP_MAPS_API_KEY": os.getenv("AMAP_API_KEY", ""),
            },
        },
        # 自研桌面 TXT 统计 Server（Python，需在 mcp_tools 目录下启动）
        "txt-counter": {
            "transport": "stdio",
            "command": sys_executable(),
            "args": ["txt_counter.py"],
            "env": _base_env(),
        },
    }
    return registry[name]


def sys_executable() -> str:
    """当前 Python 解释器绝对路径（避免环境无 python 别名导致 Server 启动失败）"""
    import sys
    return sys.executable
