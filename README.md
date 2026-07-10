# Science Workbench

一个面向人类科学家与 AI Agent 的本地优先实验仓库。它借鉴 Claude Science 的统一工作台、
渐进式技能加载、可审计产物、协调者/审阅者分离与本地计算理念，同时保持供应商中立。

本仓库是**框架仓库**。真实研究通过 `science init` 生成独立、固定契约版本的项目副本；
未来的云平台负责协调和计算，但项目仓库仍是可移植的科学事实来源。

本地开发采用自举（dogfooding）：`dogfood/framework-self-study` 使用同一套项目、实验、
Campaign 和审阅契约研究框架自身。研究项目是开发验证装置，最终交付物仍是本框架；
经审阅的发现才进入框架代码，随后以新 revision 重复实验。

## 核心闭环

```text
问题 → 可证伪假设 → 预注册协议 → 可执行代码 → 带哈希的运行记录 → 独立审阅 → 解释/发布
```

实验不是一段聊天记录，而是一个可版本化目录；结论必须能回到输入、代码、环境和运行记录。

## 快速开始

```powershell
python -m pip install -e ".[dev]"
python -m science_repo.cli validate
python -m science_repo.cli run linear-demo
python -m science_repo.cli review linear-demo
```

创建独立研究项目：

```powershell
science init ..\my-research --name "My Research" --id my-research --owner "lab"
science --project ..\my-research new first-experiment --title "A falsifiable question"
```

新建实验：

```powershell
python -m science_repo.cli new my-question --title "My falsifiable question" --owner "lab-name"
```

先读 [Agent 导航](docs/INDEX.md) 与 [实验工作流](docs/operations/experiment-workflow.md)。
框架开发者还应阅读 [自研究开发循环](docs/operations/dogfooding.md)。

## 设计边界

- 当前版本是仓库内核，不是完整桌面 UI、数据库或 HPC 调度器。
- 默认只执行清单中的 argv 数组，不经过 shell；远程计算/仪器应由受控 connector 承担。
- 自动审阅仅验证过程与产物完整性，不能替代统计、领域、伦理或同行评审。
