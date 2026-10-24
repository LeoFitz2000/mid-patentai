---
name: patent-llamaindex
description: 对本项目取得的 Google Patents 原文建立 LlamaIndex 索引，进行同义词感知的候选证据检索并保留来源。适用于证据定位，不承担新颖性或法律等同判断。
---

# 原文检索 skill

实现：[skills/llamaindex_skill.py](../../../skills/llamaindex_skill.py)。同义词：[config/synonyms.json](../../../config/synonyms.json)。

- `PatentRetriever` 使用真实 LlamaIndex 和本地 TF-IDF 嵌入，不需要外部嵌入服务，不把词面基线称作通用语义模型。
- 检索规范化术语，输出原始段落、文献编号、位置、URL 和快照哈希。不要把规范化后的文本冒充原文引文。
- 四层查询扩展由 `modules.synonym_expansion` 负责，LLM新词只用于查询，不自动写入本skill的嵌入归一化词典。理论/工程的不同预算、漂移过滤和成对Recall/Precision/成本Eval见 `docs/synonym-expansion.md`。
- 人工维护领域同义词；中英术语、大小写和空格变体需要有基础用例。冲突词组必须拒绝。
- 检索同义不等于技术含义完全一致，更不等于法律等同。温度/压力、串联/并联、数值差异、肯定/否定不得被规范成同义。
- 未知词保留待复核；不得因召回低或未匹配就标记不存在该特征。
- 基础 eval：`python -m unittest tests.test_novelty_skills.LlamaIndexSkillEvals -v`。扩展另运行 `python -m unittest tests.test_synonym_expansion tests.test_synonym_ui -v`；冻结合成池只验证工程流程，不代表Google Patents全库召回。

验收：同义词查询找到相同原文，原文不改写、分数有限；自动候选始终保持 `unknown` 状态等待复核。
