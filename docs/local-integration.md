# 材料接手与案件留存

本扩展基于 `dalynspade-base/mid-patentai` 的 `18d473932f2e6cc13db945bd0ccaaab04c444de8`；材料接手部分参考 `LeoFitz2000/patent-precheck` 的 `60868823e2b56e6663820f707e7597cce75017e1`。保留原有流程、来源说明、报告与评测记录。

## 已接入的最小流程

在原有网页中描述想法或上传 PDF、DOCX、TXT、MD、PNG/JPEG，保存为 `.local/cases/case-.../`。最多 8 份、合计 10 MB，原字节与 SHA-256 留存；网页保存不调用模型，不表示附件已经解析。

在本项目对应的 AI 工作区说“开始初筛”，Agent 按新增技能读取实际材料，写出带材料出处和未知项的 `prepared_features.json`。返回网页点击“载入 AI 整理的要素”，接入现有检索、快照、对照和判断流程。AI 客户端需要具备读取文件的工具；附件读取或解析失败应记录缺口。要素文件使用案件编号及清单哈希绑定原材料，载入不会将 AI 输出标为人工复核。重新打开网页后可选择“已保存的案件”继续。

这版保留原有人工复核关卡和判断规则。网页自动提取附件、自动语义复核及自动完成整个链路仍属后续工作；当前没有新增模型 API 调用。用户仍可沿用原有手填要素流程。

报告可下载，也可点击“保存本轮结果到案件”，每次在 `results/run-.../` 新建 Markdown/JSON，追加报告保存事件。原始清单与附件不改，旧报告不覆盖。真实案件、依赖环境及测试材料由 Git 忽略。

## 启动和验证

按 README 安装 requirements.txt 到 `.venv-novelty` 后，在项目目录运行 `powershell -ExecutionPolicy Bypass -File start_novelty.ps1`，或 `.venv-novelty/Scripts/python.exe -m streamlit run app.py --server.address 127.0.0.1`。依赖环境不随 Git 同步，每台设备需分别安装。

测试使用 `.venv-novelty/Scripts/python.exe -X utf8 -m unittest discover -s tests -v`。原有基础 eval 使用 `.venv-novelty/Scripts/python.exe -X utf8 -m skills.deepeval_skill --output .local/verification/basic_eval.json`，新记录留在独立目录，不覆盖组员提交的报告。测试和合成 eval 不代表实际专利专业准确率。

本轮已在独立环境复跑：39 项测试通过（原有 31 项，加新增 8 项）；34 项合成 eval 通过（20 + 10 + 4）；依赖一致性和新增技能静态校验通过。实际记录位于 `.local/verification/run-20261020-094028/`。没有调用付费模型或处理真实案件；AI 整理的衔接通过构造材料验证，完整自动化的专业判断能力尚未验证。

## 来源与后续协作

`material_cases.py` 改编自 patent-precheck 的材料大小/后缀约束、附件命名清理、原字节哈希、不可覆盖案件和独立结果思路；`material_ui.py` 将入口接入现有 Streamlit；新增 Skill 改编其自动接手、原文核查、预算和未知管理规则。仅引入可复用代码与规则，不包含个人记录、真实案件、密钥、旧工程或历史实验包。

团队成员通过同一个主仓库协作，分别拉取代码并安装环境。`.local/` 与测试构造材料被忽略，不通过普通 Git 提交同步。
