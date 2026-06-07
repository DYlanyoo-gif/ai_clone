# Open Source Integration Audit

Last updated: 2026-06-05

This document honestly tracks every capability module in the AI Clone project, the corresponding open-source GitHub project, current integration status, and next steps. No capability is overstated.

**当前主线（2026-06）：资料解析 → 证据提取 → 深度画像 → 风格卡 → 分析报告导出。mem0 为可选长期记忆，不是当前主线。**

## Capability Matrix

| 能力模块 | 当前实现 | 对应开源项目 | 当前状态 | 下一步 |
|---------|---------|-------------|---------|-------|
| **文档解析** | MinerU CLI 调用适配器 | [opendatalab/MinerU](https://github.com/opendatalab/MinerU) | ✅ 已真实接入 | PDF/Office/图片 → Markdown |
| **大模型分析 & 报告** | OpenAI-compatible API 调用 | [DeepSeek](https://api.deepseek.com) | ✅ 已真实接入 | 14 模块画像 + evidence_map 证据链 |
| **人物风格蒸馏** | SkillTemplate + Persona Skill Foundry + Website Runtime + Runtime Validation + External Feedback Loop | [nuwa-skill](https://github.com/alchaincyf/nuwa-skill) / [colleague-skill](https://github.com/titanwings/colleague-skill) | 🧩 L4/L5a/L5b + Website Runtime 可站内验证；L5c 需外部回填 | 生成兼容包、结构验证、dry-run、站内运行、runtime 测试用例、外部结果回填 |
| **RAG 检索** | Qdrant + FastEmbed（可选）/ 自研 n-gram fallback | [qdrant/qdrant-client](https://github.com/qdrant/qdrant-client) / [qdrant/fastembed](https://github.com/qdrant/fastembed) | 🔧 可选接入 + fallback | 默认关闭，启用后优先语义检索 |
| **长期记忆** | SQLite + mem0ai (可选) | [mem0ai/mem0](https://github.com/mem0ai/mem0) | 🔧 可选接入（非主线） | 默认关闭，不影响证据画像主线 |
| **数据集构建** | 自研 JSONL 导出 + evidence metadata | [Easy Dataset](https://github.com/ConardLi/easy-dataset) | 🔶 格式兼容导出 | 标准 JSONL，含证据信息 |
| **微调训练** | 仅导出 SFT 数据 + 证据样本 | [LLaMA Factory](https://github.com/hiyouga/LLaMA-Factory) | 🔶 格式兼容导出 | 保持导出，不在本轮实际训练 |
| **向量检索** | Qdrant local on-disk collection per profile | Qdrant / FastEmbed | 🔧 可选接入 | `VECTOR_ENABLED=true` 后启用 |
| **嵌入模型** | FastEmbed 本地 embedding | BAAI/bge-small-zh-v1.5 | 🔧 可选接入 | 需手动安装 `fastembed` |

## Status Legend

| 状态 | 含义 |
|------|------|
| ✅ 已真实接入 | 代码中真实调用该项目的 CLI/SDK/API，非骨架 |
| ⚠️ 模板理念接入 | 参考了项目的模板理念和结构，但未复制源码或调用其 API |
| 🔶 格式兼容导出 | 生成该工具可直接消费的标准格式文件，但工具本身未安装 |
| 🔶 fallback 自研 | 有自研实现，预留外部项目接入点，当前不依赖外部 |
| 🔧 可选接入 | 代码中已有真实适配器，但默认关闭，需用户手动安装依赖并启用 |
| 🧩 external submodule + 兼容包生成 | 原仓库已导入 `external/`，本项目读取契约并生成兼容文件包；不自动调用原 CLI/采集器/宿主安装器 |
| 🧩 L4/L5a/L5b 可验证 | L4=生成兼容包；L5a=结构验证；L5b=本地 dry-run；Website Runtime=站内 LLM 运行 Skill 包；L5c=外部 runtime 真实执行并回填审计 |
| ❌ 未接入 | 仅配置预留，尚未实现 |
| 📋 后续计划 | 未来版本考虑 |

## Detailed Notes

### MinerU (opendatalab/MinerU)
- **接入方式**: 通过 `subprocess` 调用 `mineru` CLI，非 Python SDK
- **适配器**: `backend/app/integrations/mineru_adapter.py`
- **检测方式**: `mineru --version` 或 `magic-pdf --version`
- **配置项**: MINERU_BACKEND, MINERU_METHOD, MINERU_LANG, MINERU_FORMULA, MINERU_TABLE, MINERU_IMAGE_ANALYSIS, MINERU_TIMEOUT_SECONDS
- **默认命令**: `mineru -p <input> -o <output> -b pipeline -m auto -l ch`
- **依赖**: 需用户手动安装 `mineru[all]`

### DeepSeek
- **接入方式**: OpenAI-compatible HTTP API (`https://api.deepseek.com`)
- **实现**: `backend/app/services/llm_provider.py` → `DeepSeekProvider`
- **模型**: deepseek-v4-flash (普通), deepseek-v4-pro (分析/聊天)
- **依赖**: 仅需 `httpx`，无额外 SDK

### nuwa-skill / colleague-skill (Persona Skill Foundry)
- **外部仓库**:
  - `external/nuwa-skill` → https://github.com/alchaincyf/nuwa-skill
  - `external/colleague-skill` → https://github.com/titanwings/colleague-skill
- **适配器**:
  - `backend/app/integrations/nuwa_skill_adapter.py`
  - `backend/app/integrations/colleague_skill_adapter.py`
  - `backend/app/integrations/skill_foundry_common.py`
- **保留旧模板层**: `backend/app/skill_templates/` 仍用于画像、聊天和 Skill Card 导出。
- **新增能力**: 读取外部 README / SKILL / references / prompts 契约，将 AI Clone 已生成的 profile portrait、style_card、evidence_map 转为兼容包。
- **Website-native Skill Runtime**:
  - `backend/app/services/skill_runtime_service.py`
  - API: `/api/profiles/{id}/skills/{skill_id}/run`
  - API: `/api/profiles/{id}/skills/{skill_id}/runs`
  - API: `/api/profiles/{id}/skills/compare-run`
  - API: `/api/profiles/{id}/skills/{skill_id}/runs/{run_id}/feedback`
  - 读取生成目录中的实际 `SKILL.md`、persona/work/thinking/evidence/manifest 文件。
  - 使用当前网站 LLM Provider 做站内测试，不访问外部 Codex / Claude Code / Hermes。
  - 运行结果写入 `skill_runtime_runs`，反馈写入 `skill_runtime_feedback`；负向反馈可追加 `correction_history.md`，但不自动重写 Skill。
- **Runtime Validation**:
  - `backend/app/integrations/skill_runtime_validator.py`
  - `backend/app/integrations/skill_installer.py`
  - `backend/app/integrations/skill_runtime_testcases.py`
  - API: `/api/profiles/{id}/skills/{skill_id}/validate`
  - API: `/api/profiles/{id}/skills/{skill_id}/dry-run`
  - API: `/api/profiles/{id}/skills/{skill_id}/install-instructions`
  - API: `/api/profiles/{id}/skills/{skill_id}/runtime-testcases`
  - API: `/api/profiles/{id}/skills/{skill_id}/runtime-results`
  - API: `/api/profiles/{id}/skills/{skill_id}/runtime-results/evaluate`
- **External Runtime Feedback Loop**:
  - AI Clone 生成 `runtime_test_cases.md` 与 `runtime_test_cases.json`。
  - 用户将 ZIP 安装到 Codex / Claude Code / Hermes / generic runtime 后手动运行测试。
  - 用户把外部 runtime 输出粘贴回网站。
  - 系统评估回填内容，满足硬条件后才记录 L5c。
  - 不自动调用外部 runtime，不伪造 `L5c actual runtime tested`。
- **输出目录**: `generated_skills/{profile_slug}/nuwa/` 与 `generated_skills/{profile_slug}/colleague/`
- **前端入口**: ProfileDetailPage 的 `Persona Skill Foundry` 区块，支持查看契约、生成兼容包、Website Runtime Lab、外部结果回填、下载 ZIP。
- **未执行**:
  - 未调用 Nuwa 原始多 agent 调研流程。
  - 未调用 colleague/dot-skill 的 Feishu/DingTalk/Slack 采集器。
  - 未调用 `tools/skill_writer.py` 或 `install_*_skill.py` 安装到宿主。
- **原因**: AI Clone 当前已有 MinerU / DeepSeek / evidence_map 主流程；本轮目标是将现有人物档案蒸馏为兼容包，而不是替换资料采集和画像系统。
- **安全边界**: `source_manifest.json` 只包含文件元数据和证据摘要，不打包原始上传文件、数据库、`.env`、API Key 或 Git remote。

#### L0-L5 接入层级

| 项目 | 当前层级 | 证据 | 限制 | 下一步 |
|------|----------|------|------|--------|
| nuwa-skill | L4 生成；L5a/L5b 可站内验证；Website Runtime 可站内运行；L5c 仅来自回填审计 | `.gitmodules` + `external/nuwa-skill` + `/api/integrations/nuwa/*` + validate/dry-run/run/runtime-results API | 未调用原始 CLI；未执行 Nuwa 多 agent 网络调研；不自动运行外部 runtime；Website Runtime 不计作 L5c | 用户生成测试用例，在外部 runtime 手动运行并回填；通过评估后记录 L5c |
| colleague-skill / dot-skill | L4 生成；L5a/L5b 可站内验证；Website Runtime 可站内运行；L5c 仅来自回填审计 | `.gitmodules` + `external/colleague-skill` + `/api/integrations/colleague/*` + validate/dry-run/run/runtime-results API | 未调用采集器、writer、install_*；不自动采集 Feishu/DingTalk/Slack；不自动运行外部 runtime；Website Runtime 不计作 L5c | 用户生成测试用例，在外部 runtime 手动运行并回填；通过评估后记录 L5c |
| Qdrant / FastEmbed | L4 可选运行层 | `backend/app/integrations/vector_adapter.py` + status/rebuild/search API | 默认关闭；未安装依赖时 fallback | 可增加更多 embedding provider |
| mem0 | L2 可选状态层 | status/rebuild/search API | 非当前主线，保持可选 | 不强化 |

### mem0 (mem0ai/mem0)
- **接入方式**: Python SDK (`mem0ai`)，可选安装
- **适配器**: `backend/app/integrations/mem0_adapter.py`
- **默认状态**: 关闭 (MEM0_ENABLED=false)
- **Fallback**: SQLite chat_messages
- **依赖**: `pip install mem0ai` (用户手动)
- **验证**: `GET /api/integrations/mem0/status` → `installed + enabled + available = true`
- **验收**: 聊天中告诉 AI 偏好 → 几轮后问"我的偏好是什么" → AI 能从长期记忆中检索

### Qdrant + FastEmbed
- **接入方式**: Python SDK，可选安装
- **适配器**: `backend/app/integrations/vector_adapter.py`
- **默认状态**: 关闭 (VECTOR_ENABLED=false)
- **存储方式**: Qdrant local on-disk，不要求启动外部 Qdrant 服务
- **默认路径**: `../data/qdrant`
- **默认 embedding 模型**: `BAAI/bge-small-zh-v1.5`
- **Fallback**: 关键词 n-gram 检索 (`search_chunks_local`) 始终保留
- **依赖**: `pip install qdrant-client fastembed` (用户手动)
- **验证**: `GET /api/integrations/vector/status` → `installed + enabled + available = true`
- **重建索引**: `POST /api/profiles/{id}/vector/rebuild`
- **测试检索**: `GET /api/profiles/{id}/vector/search?query=...`
- **注意**: 向量写入失败只记录 warning，不影响上传、聊天或分析主流程

### Easy Dataset
- **接入方式**: 格式兼容导出，不安装原项目
- **适配器**: `backend/app/integrations/easy_dataset_adapter.py`
- **导出格式**: JSONL，每行 `{profile_id, profile_name, source_document, chunk_id, text, metadata}`

### LLaMA Factory
- **接入方式**: 格式兼容导出，不安装原项目
- **适配器**: `backend/app/integrations/llamafactory_adapter.py`
- **导出格式**: JSONL，每行 `{messages: [{role, content}, ...]}`
- **注意**: LLaMA Factory 需要 PyTorch + GPU，不在本项目安装范围内

## Current Running Projects (Honest Summary)

### Actually Installed & Running
1. **DeepSeek** — LLM analysis and chat (via API, no local install)
2. **MinerU** — Document parsing (via CLI, user-installed)

### Optional Integration (Install to Enable)
3. **mem0** — Long-term memory
   - Install: `pip install mem0ai`
   - Enable: set `MEM0_ENABLED=true` in `.env`, restart backend
   - Verify: `GET /api/integrations/mem0/status` returns `available: true`
   - Fallback: SQLite chat_messages (always works, no mem0 needed)

4. **Qdrant + FastEmbed** — Semantic evidence retrieval
   - Install: `pip install qdrant-client fastembed`
   - Enable: set `VECTOR_ENABLED=true` in `.env`, restart backend
   - Verify: `GET /api/integrations/vector/status` returns `available: true`
   - Rebuild: `POST /api/profiles/{id}/vector/rebuild`
   - Fallback: keyword retrieval (always works, no vector dependencies needed)

### Format-Compatible Export (No Install Needed)
5. **Easy Dataset** — RAG dataset JSONL export
6. **LLaMA Factory** — SFT training data JSONL export

### External Repo Imported + Compatible Package
7. **nuwa-skill / colleague-skill** — Persona Skill Foundry
   - Submodules: `external/nuwa-skill`, `external/colleague-skill`
   - APIs: `/api/integrations/nuwa/*`, `/api/integrations/colleague/*`, `/api/profiles/{id}/skills/*`
   - Validation: structure validator + dry-run simulator + external runtime feedback loop available
   - Original CLI invoked: no
   - Actual runtime invoked by AI Clone: no
   - L5c: only when user manually installs, runs generated test cases outside AI Clone, and pastes results back for evaluation
   - Reason: AI Clone generates compatibility packages from existing evidence profiles; it does not run external collectors or host installers automatically.

### Not Yet Running
8. **Chroma** — Alternative vector database (not implemented)
9. **LLaMA Factory training** — Actual fine-tuning (requires GPU, out of scope)
