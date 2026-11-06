#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
DeepEval 评估脚本 - 投顾AI助手质量测试

本模块属于"金融场景多架构 Agent 套件"个人项目，对应架构模式：DeepEval 效果评估（针对混合式投顾助手）。

使用 DeepEval 对投顾AI助手进行自动化质量评估，包括：
1. 答案相关性评估 - 回答是否切题
2. 幻觉检测 - 是否编造虚假信息
3. 自定义评估 - 是否考虑客户风险偏好

安装依赖：
    pip install deepeval

运行方式（在项目根目录下执行）：
    方式1: python evaluation/deepeval_wealth_advisor.py
    方式2: deepeval test run evaluation/deepeval_wealth_advisor.py

环境变量（评估器与被测 Agent 共用 OpenAI 兼容端点）：
    OPENAI_API_KEY: OpenAI 兼容协议 API 密钥
    OPENAI_BASE_URL: OpenAI 兼容协议端点（DeepEval 的 OpenAI 客户端会自动读取该变量）
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from dotenv import load_dotenv

# DeepEval 导入
from deepeval import evaluate
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.models import OpenAIModel
from deepeval.metrics import (
    AnswerRelevancyMetric,
    HallucinationMetric,
    GEval
)

# 加载项目根目录下的 .env 配置
load_dotenv()

# 将项目根目录加入模块搜索路径，以便导入混合式投顾助手包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 导入投顾助手（混合式架构模块）
from hybrid_advisor.hybrid_wealth_advisor_langgraph import (
    run_wealth_advisor,
    SAMPLE_CUSTOMER_PROFILES
)

# 评估器模型（与被测 Agent 共用同一 OpenAI 兼容端点）
EVAL_MODEL = "qwen3.7-plus"


def get_eval_model() -> OpenAIModel:
    """构造指向 OpenAI 兼容端点的评判模型

    DeepEval 若只传 model 字符串会默认连 OpenAI 官方 api.openai.com，
    必须显式传入 base_url 与 api_key 指向兼容端点（token-plan），否则 Connection error。
    """
    base_url = os.getenv(
        "OPENAI_BASE_URL",
        "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    return OpenAIModel(
        model=EVAL_MODEL,
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=base_url,
    )


# ==================== 测试用例定义 ====================

# 反应式查询测试用例（简单查询）
REACTIVE_TEST_CASES = [
    {
        "input": "今天上证指数表现如何？",
        "customer_id": "customer1",
        "context": ["上证指数是中国股市的重要指标", "提供实时行情数据"],
        "expected_keywords": ["上证指数", "点位"]
    },
    {
        "input": "请解释一下什么是ETF？",
        "customer_id": "customer1",
        "context": ["ETF是交易所交易基金", "可以在交易所买卖"],
        "expected_keywords": ["ETF", "基金", "交易"]
    },
]

# 深思熟虑查询测试用例（复杂分析）
DELIBERATIVE_TEST_CASES = [
    {
        "input": "根据我的风险偏好，应该如何调整投资组合？",
        "customer_id": "customer1",
        "context": [
            "客户风险评级：平衡型",
            "当前配置：股票40%，债券30%，现金10%，另类投资20%",
            "投资期限：中期"
        ],
        "expected_keywords": ["风险", "配置", "建议"]
    },
    {
        "input": "请帮我制定一个退休投资计划",
        "customer_id": "customer2",
        "context": [
            "客户风险评级：进取型",
            "财务目标：财富增长、资产配置多元化",
            "投资期限：长期"
        ],
        "expected_keywords": ["退休", "规划", "投资"]
    },
]


# ==================== 辅助函数 ====================

def run_agent_and_get_response(query: str, customer_id: str) -> Dict[str, Any]:
    """运行投顾助手并获取响应"""
    print(f"\n[测试] 运行查询: {query[:50]}...")
    result = run_wealth_advisor(user_query=query, customer_id=customer_id)
    return result


def create_test_case(
    test_data: Dict[str, Any],
    actual_output: str,
    retrieval_context: List[str]
) -> LLMTestCase:
    """创建 DeepEval 测试用例"""
    return LLMTestCase(
        input=test_data["input"],
        actual_output=actual_output,
        retrieval_context=retrieval_context
    )


# ==================== 评估指标定义 ====================

def get_metrics():
    """获取评估指标列表"""
    eval_model = get_eval_model()

    # 1. 答案相关性：评估回答是否与问题相关
    relevancy_metric = AnswerRelevancyMetric(
        threshold=0.6,
        model=eval_model,
        include_reason=True
    )

    # 2. 幻觉检测：检测是否编造虚假信息
    hallucination_metric = HallucinationMetric(
        threshold=0.5,
        model=eval_model,
        include_reason=True
    )

    # 3. 自定义评估：是否考虑客户风险偏好
    risk_consideration_metric = GEval(
        name="RiskConsideration",
        criteria="评估投资建议是否考虑了客户的风险承受能力和投资偏好",
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT
        ],
        evaluation_steps=[
            "检查回答是否提及风险相关内容",
            "评估建议是否与客户风险等级匹配",
            "判断是否有个性化的考虑"
        ],
        threshold=0.5,
        model=eval_model
    )

    return [relevancy_metric, hallucination_metric, risk_consideration_metric]


# ==================== 主评估流程 ====================

def run_evaluation():
    """运行完整评估流程"""

    print("=" * 60)
    print("DeepEval 投顾AI助手评估")
    print("=" * 60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 合并所有测试用例
    all_test_data = REACTIVE_TEST_CASES + DELIBERATIVE_TEST_CASES

    # 创建测试用例列表
    test_cases = []

    print(f"[准备] 共 {len(all_test_data)} 个测试用例")
    print("-" * 60)

    # 遍历测试数据，运行 Agent 并创建测试用例
    for i, test_data in enumerate(all_test_data, 1):
        print(f"\n[{i}/{len(all_test_data)}] 测试: {test_data['input'][:40]}...")

        # 运行投顾助手
        result = run_agent_and_get_response(
            query=test_data["input"],
            customer_id=test_data["customer_id"]
        )

        # 获取实际输出
        actual_output = result.get("final_response", "")

        if not actual_output:
            print(f"  [警告] 未获取到响应，跳过此用例")
            continue

        print(f"  [响应] {actual_output[:100]}...")

        # 获取客户信息作为上下文
        customer_profile = SAMPLE_CUSTOMER_PROFILES.get(test_data["customer_id"], {})
        retrieval_context = test_data["context"] + [
            f"客户风险等级: {customer_profile.get('risk_tolerance', '未知')}",
            f"投资期限: {customer_profile.get('investment_horizon', '未知')}"
        ]

        # 创建测试用例
        test_case = create_test_case(
            test_data=test_data,
            actual_output=actual_output,
            retrieval_context=retrieval_context
        )
        test_cases.append(test_case)

    print("\n" + "=" * 60)
    print(f"[评估] 开始评估 {len(test_cases)} 个测试用例")
    print("=" * 60)

    # 获取评估指标
    metrics = get_metrics()
    print(f"[指标] 使用 {len(metrics)} 个评估指标:")
    for m in metrics:
        print(f"  - {m.__class__.__name__}")

    # 运行评估（DeepEval 4.x：print_results 移入 display_config，默认即为打印结果）
    print("\n[运行] 正在评估...")
    results = evaluate(
        test_cases=test_cases,
        metrics=metrics
    )

    print("\n" + "=" * 60)
    print("评估完成")
    print("=" * 60)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return results


# ==================== Pytest 风格测试（可选） ====================

def test_reactive_query():
    """测试反应式查询（Pytest 风格）"""
    from deepeval import assert_test

    test_data = REACTIVE_TEST_CASES[0]
    result = run_agent_and_get_response(
        query=test_data["input"],
        customer_id=test_data["customer_id"]
    )

    test_case = LLMTestCase(
        input=test_data["input"],
        actual_output=result.get("final_response", ""),
        retrieval_context=test_data["context"]
    )

    metric = AnswerRelevancyMetric(threshold=0.6, model=EVAL_MODEL)
    assert_test(test_case, [metric])


def test_deliberative_query():
    """测试深思熟虑查询（Pytest 风格）"""
    from deepeval import assert_test

    test_data = DELIBERATIVE_TEST_CASES[0]
    result = run_agent_and_get_response(
        query=test_data["input"],
        customer_id=test_data["customer_id"]
    )

    customer_profile = SAMPLE_CUSTOMER_PROFILES.get(test_data["customer_id"], {})

    test_case = LLMTestCase(
        input=test_data["input"],
        actual_output=result.get("final_response", ""),
        retrieval_context=test_data["context"] + [
            f"客户风险等级: {customer_profile.get('risk_tolerance', '未知')}"
        ]
    )

    metrics = [
        AnswerRelevancyMetric(threshold=0.6, model=EVAL_MODEL),
        HallucinationMetric(threshold=0.5, model=EVAL_MODEL)
    ]
    assert_test(test_case, metrics)


# ==================== 入口 ====================

if __name__ == "__main__":
    # 检查环境变量（评估器与被测 Agent 共用同一 OpenAI 兼容端点配置）
    if not os.getenv("OPENAI_API_KEY"):
        print("[错误] 请设置 OPENAI_API_KEY 环境变量")
        print("DeepEval 评估器与投顾助手均通过 OpenAI 兼容协议调用模型")
        print()
        print("设置方式 (Linux/Mac):")
        print('  export OPENAI_API_KEY="sk-your-key-here"')
        exit(1)

    # 运行评估
    run_evaluation()
