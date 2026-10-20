---
name: patent-deepeval
description: 运行本 Harness 三个 skill 的离线基础 eval，检查新颖性误判边界、同义词召回和裁判自身的正负对照，输出逐条回归记录。适用于开发回归，不是实际专利专业准确率认证。
---

# 基础评测 skill

实现：[skills/deepeval_skill.py](../../../skills/deepeval_skill.py)。案例：[evals/basic_cases.json](../../../evals/basic_cases.json)。

- 从根目录运行 `python -m skills.deepeval_skill`，默认在 `.local/evaluations/` 创建新记录；也可用 `--output 新文件.json`，不覆盖已有结果。
- 使用真实 DeepEval 的 `BaseMetric` 与 `LLMTestCase`，按作者编写的教学参考标签作确定性评分，不需要模型密钥或云平台；不能称为独立专业标注。
- 每个 skill 都必须在报告中有独立统计和逐条结果。评测裁判自身也要通过正确、错误、缺引用和坏 JSON 四类测试。
- 原表中的 FTO 情形保留为越界测试；本工具不得为了通过用例而输出侵权结论。
- 当前案例明确标记为教学合成题，不可计为真实专利金标准。新增真实题需记录来源快照、基准日、要素、引用与专业标注，并隔离盲测集。
- 分组工程回归使用 `python tools/run_verification.py --output-dir 新目录`，当前工程与旧模块兼容测试分列；内部重复调用的34条合成eval不与测试数相加。
- 真实来源比较另用 `python tools/run_real_patent_eval.py --source-dir 来源目录 --output-dir 新目录`；只有 `--fetch-sources` 才访问两篇公开页面，默认显式快照离线比较。真实运行没有合格独立参考时，漏报/误放为null，不能写0或声称专业正确率。AI草案不改名为人工参考，不预设原方案risk、变更版未发现。详见 `docs/real-evaluation.md`。
- 修改模型、提示词、术语表、规则或检索后重跑；失败返回非零退出状态，不删除失败案例以提高分数。
- 基础 eval：`python -m unittest tests.test_novelty_skills.DeepEvalSkillEvals -v`。

验收：报告含数据版本、三个依赖版本、逐条结果；所有关键测试通过才能标记本轮回归通过。
