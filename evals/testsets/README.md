# 语义 Eval 测试集（理论集 + 工程集）

仿照课堂作业 rsi-lab（`F:\Agent Collaboration\课堂作业\rsi-lab`）的打分系统，为本项目（mid-patentai 2.0.0）构建的语义 eval 测试集。语料取自 **10 篇真实公开专利**（2026-11-04 从 Google Patents 逐字核验），覆盖本项目"六维语义验收 + 四类业务结论 + 决策规则引擎"的测试需求。

## 与 rsi-lab 的对应关系

| rsi-lab | 本目录 |
|---|---|
| `policy.py` 评分细则（代码化真值，被测 Agent 不可见） | `policy.py` 细则条文（R01–R14）+ 各 cases JSON 里的 `label`/`expected` 字段 |
| `data/train.json`（36 份，循环用） | `theory_cases.json` / `engineering_cases.json` 中 `usage: "train"` 的案例 |
| `data/anchor.json`（40 份，从不参与决策，只对账） | 同上 `usage: "anchor"` 的案例（`--split anchor` 查看锚集对账） |
| `audit.py`（用细则答案给每轮候选对账） | `score.py`（对冻结候选输出 / 规则引擎输出对账） |
| `check.py`（环境自检） | `score.py` 工程集部分（离线、零模型、零网络） |

## 文件

| 文件 | 内容 |
|---|---|
| `patents.json` | 10 篇真实专利语料：公开号、标题、日期、逐字摘录（摘要/权利要求/说明书段），含机器翻译痕迹原文保留 |
| `theory_cases.json` | **理论集**：19 案（训练 13 / 锚 6），每案 = 真实原文 + 冻结候选输出 + 隐藏细则答案（六维违反、业务结论、语义裁决） |
| `engineering_cases.json` | **工程集**：18 案（决策 14 / 契约 4），对齐 `modules/novelty_rules.assess_novelty` 与 `modules/novelty_models` 数据契约 |
| `policy.py` | 细则条文（R01 引文逐字 … R14 裁决推导）与空白归一化工具 |
| `score.py` | 对账打分器（见下） |

## 语料（10 篇，全部逐字核验）

| 公开号 | 公开日 | 主题 | 主要考点 |
|---|---|---|---|
| US4968168A | 1990-11-06 | 咔嗒圆珠笔 | 互斥实施例、优选措辞（preferably metal）、伪造引文 |
| US5944436A | 1999-08-31 | 发声笔 | 否定词（cannot engage）、指称对象（弹性片21 vs U形部41）、功能≠结构 |
| US8053972B2 | 2011-11-08 | 量子点白光LED（MIT） | 光致转换 vs 电致发光、正确锚定用例 |
| CN108559503B | A 2018-09-21 / B 2020-07-07 | 华中科大 Cs2AgBiBr6 制备 | 独权/从权数值界限、工序顺序、同族版本日期链、跨文献拼接 |
| US20170194101A1 | 2017-07-06 | Stanford Cs2AgBiBr6 吸收层 | 记号差异（Cs2AgBiBr6 vs Cs2BiAgBr6）→ 待裁决示范 |
| US7802572B2 | 2010-09-28 | 透明医用口罩 | 摘要 optionally vs 权利要求必要限定、自定义术语边界（transparent 含 translucent） |
| CN115863457A | 2023-03-28 | 云南师大 Cs2AgBiBr6 电池 | 摘要概括词 vs 权利要求逐层限定、数值界限、日期门、CN 抵触申请 |
| CN110408993A | 2019-11-05 | 宁波大 X 射线探测晶体 | 背景技术不是方案披露、用途限定 |
| US20240423306A1 | 2024-12-26 | 铜+银 TENG 抗菌口罩 | 例示性摘要（in some examples）≠ 权利要求限定 |
| US3664335A | 1972-05-23 | 三层外科口罩 | 单条权利要求逐项正确锚定用例 |

## 用法

```powershell
# 全部对账（理论集 + 工程集）
.\.venv-novelty\Scripts\python.exe -X utf8 evals\testsets\score.py
# 只跑某一集 / 只看锚集 / 单查一案 / 保存 JSON
.\.venv-novelty\Scripts\python.exe -X utf8 evals\testsets\score.py --set theory
.\.venv-novelty\Scripts\python.exe -X utf8 evals\testsets\score.py --split anchor
.\.venv-novelty\Scripts\python.exe -X utf8 evals\testsets\score.py --case T05
.\.venv-novelty\Scripts\python.exe -X utf8 evals\testsets\score.py --json .local\evaluations\testset-report.json
```

## 打分口径

**理论集**（候选输出 vs 细则答案）逐案检查：
1. `quote_verbatim`——disclosed 行的引文按空白归一化后能在所引小节逐字找到（R01）；
2. `section_map`——引文小节是否符合细则指定的层级（R08：摘要≠权利要求、独权≠从权）；
3. `statuses`——逐项 disclosed/not_found/unknown 是否与细则一致（R02/R05/R07/R12）；
4. `conclusion`——业务结论四选一是否正确；
5. `verdict`——候选自报裁决 vs 细则裁决（R14：有违反→needs_revision，诚实未定→pending_adjudication）；
6. `required_mentions`——必提事项（如 T15 必须提到同族 A 的公开日 2018-09-21）。

边界如实标注：纯语义问题（如 T06 工序顺序被丢弃）机械对账覆盖不到，输出标"机械未覆盖语义层，按细则裁决"，这类案例是给独立语义裁判 / 人工复核用的，正是本项目 `patent-semantic-eval` 六维裁决的入口。

**工程集**（规则引擎 vs 细则答案）：把构造输入喂给真实 `assess_novelty`，比较返回的四类结论；契约用例直接调用 `google_patent_url`、快照哈希绑定、`parse_features`、快照版本校验。全部离线、确定、可重复。

## label 纪律

- label 由 `policy.py` 的细则从原文事实推导；**被测流程不得读取 label/expected 字段**（与 rsi-lab"Agent 看不到 policy.py"同口径）。
- `usage: anchor` 的案例（理论 T05/T10/T13/T14/T15/T17，工程 E14）**不参与任何迭代调优**，只用于对账。
- 首次对账记录：**E04 的细则答案曾被纠正**——初版基准日取 2023-06-01（在公开日之后），引擎正确判 potential_novelty_risk，label 错；修正基准日为 2022-12-15（落在申请日 2022-11-30 与公开日 2023-03-28 之间）后 18/18 一致。对账机制本身抓住了细则错误，这正是锚集的用途。

## 当前对账结果（2026-11-04，commit e49f9a7）

- 工程集：**18/18 与细则一致**（14 决策 + 4 契约）。
- 理论集：19 案全部按设计对账——16 个 needs_revision 案例中 15 个被机械对账捕获（T19 伪造引文、T02 否定词、T07 可选/必要、T15 日期链等），1 个（T06 工序顺序）如实标注需语义裁判；T13/T17 为正确锚，T14 为待裁决示范。
- 仓库自身校验未受影响：`tools/run_verification.py --current-only` 全部通过（`all_engineering_checks_passed: true`，记录于 `.local/verification/testset-addition-check`）。

## 诚实边界

- 工程集的逐项复核（rows）是**构造输入**，不是真实人工复核；理论集的候选输出是**冻结的模拟业务输出**，有对有错，用于对账训练，不代表任何真实模型的水平。
- 本测试集衡量的是"输出与细则答案的一致性"，**不是**专业准确率、召回率或语义质量分数；与项目 README 的口径一致，不输出数值评分。
- 语料为 Google Patents 页面逐字转录，机器翻译痕迹（如 `Cs (volatile organic Compounds)2AgBiBr6`、`turpentine absolute alcohol`、`tHe`）原样保留，引文核对按空白归一化，不改写任何非空白字符。
- 十篇专利不足以覆盖全部现有技术空间；扩充语料时按 `patents.json` 现有格式增补并保持逐字核验。

## RSI 案例：副本 + 20 篇候选 + 5 轮循环（rsi_case.json + rsi_loop.py）

对应课堂规格“小型 RSI 构建”：对已有专利A（CN108559503B，华中科大 Cs2AgBiBr6 制备）在权利要求范围内调整参数生成**一个副本**（纯 DMSO、60℃、氯苯 1:2、30℃ 挥发——全部落在 A 的 X≥1/Y≥1/50-70℃/20-40℃ 界限内），基准日取 2018-10-08（A 族 A 版本公开日 2018-09-21 之后一周），在 20 篇候选里检验被测系统能否：①检索命中相关专利（含A，共 6 篇同材料族）；②正确排除晚于基准日的 4 篇同材料文献（日期门）；③给基准日前文献对标风险等级（A=高，Stanford=中，其余无关=低）。

- `rsi_case.json`：副本描述 + 20 篇候选的隐藏标注（expected_hit / prior_art_at_cutoff / risk + basis）；被测流程不得读取。
- `rsi_loop.py`：每轮按**临时 skill 文档**（初版只有一句笼统指令）对 20 篇候选出“相关/基准日资格/风险等级”，与隐藏标注对账打分（0.5×命中F1 + 0.5×判断全对率），失分点写回临时文档（P），分数超过历史最佳才采纳（R），默认 5 轮；临时文档只写在输出目录，**绝不修改 .agents/skills 下的既有 skill**。
- 评分定位：与 rsi-lab 的 F 信号同位，只用于循环迭代与对账，不是语义质量分（与项目六维验收“不出分”的口径不冲突——两套各司其职）。
- 已用 mock 模式端到端验证（脚本模拟裁判/提词器）：0.545→0.795→0.878→0.917→1.000，结果小文档写入 `.local/rsi/<时间戳>/rsi_result.md`；**mock 分数只验证机制，不代表模型能力**。真实模型跑法：

```powershell
$env:LLM_API_KEY="..."; $env:LLM_BASE_URL="..."; $env:LLM_MODEL="..."   # CLI 不自动读 .env
.\.venv-novelty\Scripts\python.exe -X utf8 evals\testsets\rsi_loop.py --run-model --confirm-external
```

## 后续可接

1. 把 `theory_cases.json` 的 `candidate_output` 换成真实 harness 冻结记录（`skill_records`），即可用同一打分器对账真实业务输出。
2. 理论集案例可经 `tools/run_semantic_eval.py --references` 作为独立参考喂给六维语义裁判，验证裁判与本细则的一致性。
3. 新增专利：先在 Google Patents 核验原文，按 `patents.json` 格式录入，再设计案例；细则条文如需扩展，改 `policy.py` 的 RULES 并同步 label。
