# LangSmith 追踪与评估结果解读指南

> 基于 2026-11-07 首次实测（实验 wealth-advisor-eval-20261107-010551，4 条用例全跑通，耗时 7.4 分钟）整理。

---

## 一、trace 页面上的数据分三类，来源完全不同

### 1. 反馈分数（Feedback）——评估器打的质量分

本项目定义的两个评估器，结果展示在 trace 详情的 Feedback 区域：

| 指标 | 判断逻辑 | 怎么看 |
|---|---|---|
| `processing_mode` | 对比 Agent 实际路由 vs 数据集期望路由 | score=1 路由正确，0 错误；comment 写明"期望 X 实际 Y" |
| `keyword_completeness` | 期望关键词在回答中的命中率 | score 为 0~1 比值；comment 写"命中 n/m 个关键词" |

**快速判断一个指标是做什么的：直接看 comment 字段**。每条分数都带一句人话解释打分依据，这是评估器代码里特意写的，保证分数可读、可审计。

### 2. 运行统计（平台自动采集）——成本与性能指标

trace 页顶部的 Latency / Total Tokens / Status 是 LangSmith 自动统计的，衡量的是**性能和成本**，不是质量：

- **Latency**：运行总耗时。反应式约 10 秒、深思熟虑 2~6 分钟——两种架构的成本差异在数据上一眼可见
- **Total Tokens**：总 token 消耗，可下钻到每个 LLM 调用节点
- **Status**：success / error，配合 trace 树定位失败节点

### 3. 树节点输入输出——追溯"分数为什么是这样"

质量分异常时的排查路径：

```
分数异常 → 看 comment（评估器怎么说）→ 展开 trace 树对应节点 → 检查该步的输入/输出
```

例：`keyword_completeness` 得 0.5，comment 显示"命中 1/2 个关键词"，就展开最后一个生成节点看 final_response 缺了哪个词——再判断是 Agent 没答到，还是测试用例的关键词定得不合理。

**核心认知：指标负责"发现问题"，trace 树负责"定位原因"。**

---

## 二、结果查看入口

评估通过 `evaluate()` 运行时，trace 挂在实验会话下，**不在独立的 Tracing 项目里**：

1. 左侧栏 **Datasets & Experiments**
2. 点数据集 `wealth-advisor-test-dataset`
3. 切到 **Experiments** 标签 → 点实验名（如 `wealth-advisor-eval-20261107-010551-8fec4f66`）
4. 用例列表每行显示两个反馈分数，点任意一行 → run 链接 → 完整调用树

树结构（深思熟虑用例示例）：

```
run_wealth_advisor（总 run：总耗时/总 token）
 └── LangGraph（整个状态图）
      ├── assess（协调层路由判断）
      │    └── ChatOpenAI（该次 LLM 调用：prompt/completion/token/耗时）
      ├── collect_data → analyze_data → generate_recommendations
      └── ...（反应式用例则是 reactive_agent ⇄ tools 循环）
```

---

## 三、本次实测结果（2026-11-07）

| 项 | 结果 |
|---|---|
| 数据集 | wealth-advisor-test-dataset（4 条：2 反应式 + 2 深思熟虑） |
| 完成情况 | 4/4 全部执行成功 |
| 总耗时 | 7 分 24 秒（平均 111 秒/条，串行防限流） |
| 环境 | qwen3.7-plus + token-plan 端点，LangSmith Cloud |

**首次跑通验证的链路完整性**：本地 Agent → LangGraph 图执行 → trace 自动上报 → 评估器打分 → 网页端分数与调用树可交互查看。

---

## 四、演示要点

1. **打开一条深思熟虑 run**：先展示顶层时间轴（generate_recommendations 最耗时可一眼看出），再展开 assess 节点讲协调层路由判断
2. **对比打开一条反应式 run**：树明显浅，且能看到 tools ⇄ agent 的循环节点——两种架构差异在 trace 树上肉眼可见
3. **讲三层数据的工作流**：

> "页面上有三类数据：反馈分数是评估器打的质量分（带 comment 说明依据），延迟和 token 是平台采集的成本指标，trace 树是原始输入输出。工作流是——先看平均分发现哪类用例弱，点进具体用例看 comment，再展开 trace 树定位到具体节点。比如路由正确率掉了，我能直接看到 assess 节点那次分类的 prompt 和输出，判断是 prompt 问题还是 case 本身模糊。"

4. **若发现某条分数为 0**：不要慌，这正是好素材——当场分析是 Agent 问题还是测试用例设计问题，展示的是"用评估驱动改进"的完整闭环思维
