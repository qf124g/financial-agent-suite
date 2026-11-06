#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""基于 LangSmith 的投顾助手批量测试与效果评估

本模块属于"金融场景多架构 Agent 套件"个人项目，对应架构模式：效果评估体系。

迁移自课程实战（23 章 CASE-投顾AI助手），针对套件做了两处适配：
1. 被测对象改为套件版混合式投顾 Agent（OpenAI 兼容模式，qwen3.7-plus）
2. 环境变量采用新版 LangSmith SDK 命名（LANGSMITH_TRACING / LANGSMITH_API_KEY）

评估覆盖两类指标：
- ProcessingModeEvaluator：协调层路由是否正确（简单查询走反应式、复杂查询走深思熟虑）
- KeywordCompletenessEvaluator：回答是否覆盖期望关键词（回答完整性代理指标）

前置条件：
    export LANGSMITH_TRACING=true
    export LANGSMITH_API_KEY="你的key"   # smith.langchain.com 免费注册
    export OPENAI_API_KEY=...            # 模型调用 key

运行：
    python evaluation/langsmith_evaluation.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# 套件根目录加入路径，导入被测 Agent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hybrid_advisor.hybrid_wealth_advisor_langgraph import run_wealth_advisor

from langsmith import Client
from langsmith.evaluation import evaluate

# LangSmith 开关检查
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
LANGSMITH_ENABLED = os.getenv("LANGSMITH_TRACING", "").lower() == "true"

client = Client(api_key=LANGSMITH_API_KEY) if (LANGSMITH_ENABLED and LANGSMITH_API_KEY) else None

# ==================== 测试数据集 ====================

# 反应式查询（简单行情/概念类，应走 reactive 链路）
REACTIVE_TEST_CASES = [
    {
        "inputs": {"user_query": "今天上证指数的表现如何？", "customer_id": "customer1"},
        "expected_outputs": {"processing_mode": "reactive", "should_contain": ["上证指数"]},
    },
    {
        "inputs": {"user_query": "我的投资组合中科技股占比是多少？", "customer_id": "customer1"},
        "expected_outputs": {"processing_mode": "reactive", "should_contain": ["科技", "占比"]},
    },
]

# 深思熟虑查询（复杂规划类，应走 deliberative 链路）
DELIBERATIVE_TEST_CASES = [
    {
        "inputs": {"user_query": "考虑到我的退休目标，请评估我当前的投资策略并提供优化建议。", "customer_id": "customer1"},
        "expected_outputs": {"processing_mode": "deliberative", "should_contain": ["退休", "建议"]},
    },
    {
        "inputs": {"user_query": "我想为子女准备教育金，请帮我设计一个10年期的投资计划。", "customer_id": "customer1"},
        "expected_outputs": {"processing_mode": "deliberative", "should_contain": ["教育金", "建议"]},
    },
]

ALL_TEST_CASES = REACTIVE_TEST_CASES + DELIBERATIVE_TEST_CASES
DATASET_NAME = "wealth-advisor-test-dataset"

# ==================== 评估器 ====================
# langsmith 新版 evaluate API：评估器为函数 (run, example) -> dict

def processing_mode_evaluator(run, example) -> dict:
    """评估协调层路由模式选择是否正确（混合式架构的核心质量指标）"""
    expected = (example.outputs or {}).get("processing_mode")
    actual = (run.outputs or {}).get("processing_mode")
    if not expected:
        return {"key": "processing_mode", "score": None, "comment": "未指定期望模式"}
    if actual == expected:
        return {"key": "processing_mode", "score": 1.0, "comment": f"路由正确: {actual}"}
    return {"key": "processing_mode", "score": 0.0, "comment": f"路由错误: 期望 {expected}, 实际 {actual}"}


def keyword_completeness_evaluator(run, example) -> dict:
    """评估回答对期望关键词的覆盖率（回答完整性的代理指标）"""
    expected_keywords = (example.outputs or {}).get("should_contain", [])
    response = (run.outputs or {}).get("final_response", "")
    if not expected_keywords:
        return {"key": "keyword_completeness", "score": None, "comment": "未指定关键词"}
    found = [kw for kw in expected_keywords if kw.lower() in response.lower()]
    return {
        "key": "keyword_completeness",
        "score": len(found) / len(expected_keywords),
        "comment": f"命中 {len(found)}/{len(expected_keywords)} 个关键词",
    }

# ==================== 数据集与评估执行 ====================

def create_test_dataset() -> str:
    """创建测试数据集（已存在则复用）"""
    try:
        client.read_dataset(dataset_name=DATASET_NAME)
        print(f"[LangSmith] 数据集已存在: {DATASET_NAME}")
    except Exception:
        client.create_dataset(
            dataset_name=DATASET_NAME,
            description="混合式投顾 Agent 测试集：反应式/深思熟虑路由 + 回答完整性",
        )
        for case in ALL_TEST_CASES:
            client.create_example(
                inputs=case["inputs"],
                outputs=case["expected_outputs"],
                dataset_name=DATASET_NAME,
            )
        print(f"[LangSmith] 数据集已创建: {DATASET_NAME}（{len(ALL_TEST_CASES)} 条用例）")
    return DATASET_NAME


def target_function(inputs: dict) -> dict:
    """被测函数：跑一遍投顾 Agent，输出交给评估器打分"""
    result = run_wealth_advisor(inputs["user_query"], inputs.get("customer_id", "customer1"))
    return {
        "final_response": result.get("final_response", ""),
        "processing_mode": result.get("processing_mode", "unknown"),
        "query_type": result.get("query_type", "unknown"),
    }


def main():
    if not client:
        print("错误: LangSmith 未启用，请设置:")
        print("  export LANGSMITH_TRACING=true")
        print("  export LANGSMITH_API_KEY=你的key")
        sys.exit(1)

    dataset_name = create_test_dataset()
    experiment = f"wealth-advisor-eval-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    print(f"[LangSmith] 开始评估，实验: {experiment}（串行执行，避免限流）")

    evaluate(
        target_function,
        data=dataset_name,
        evaluators=[processing_mode_evaluator, keyword_completeness_evaluator],
        experiment_prefix=experiment,
        max_concurrency=1,
    )

    print(f"\n评估完成，到 https://smith.langchain.com 查看实验 {experiment} 的详细结果")


if __name__ == "__main__":
    main()
