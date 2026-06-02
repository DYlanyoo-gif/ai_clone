# Open Source Integration Audit

Last updated: 2026-06-02

This document honestly tracks every capability module in the AI Clone project, the corresponding open-source GitHub project, current integration status, and next steps. No capability is overstated.

## Capability Matrix

| 能力模块 | 当前实现 | 对应开源项目 | 当前状态 | 下一步 |
|---------|---------|-------------|---------|-------|
| **文档解析** | MinerU CLI 调用适配器 | [opendatalab/MinerU](https://github.com/opendatalab/MinerU) | ✅ 已真实接入 | 增加解析预览、错误重试、分页解析 |
| **大模型分析** | OpenAI-compatible API 调用 | [DeepSeek](https://api.deepseek.com) | ✅ 已真实接入 | 支持更多模型、prompt 缓存优化 |
| **人物风格蒸馏** | 自研 SkillTemplate + prompt 工程 | [nuwa-skill](https://github.com/nuwa-skill/nuwa-skill) / [dot-skill](https://github.com/dot-skill/dot-skill) | ⚠️ 模板理念接入 | 模板文件化、导入/导出、不直接复制源码 |
| **RAG 检索** | 自研 n-gram + Jaccard 评分 | 后续可接 Chroma/Qdrant/LangChain/LlamaIndex | 🔶 fallback 自研 | 保留后续计划，暂不引入重依赖 |
| **长期记忆** | SQLite chat_messages 表 | [mem0ai/mem0](https://github.com/mem0ai/mem0) | ✅ 可选接入 (2026-06) | 当前可选启用，SQLite 为 fallback |
| **数据集构建** | 自研 JSONL 导出 | [Easy Dataset](https://github.com/ConardLi/easy-dataset) | 🔶 格式兼容导出 | 标准 JSONL 格式，无需安装原项目 |
| **微调训练** | 仅导出 SFT 数据 | [LLaMA Factory](https://github.com/hiyouga/LLaMA-Factory) | 🔶 格式兼容导出 | 保持导出，不在本轮实际训练 |
| **嵌入模型** | 未接入 | OpenAI text-embedding-3-small / BGE | ❌ 未接入 | 配置预留，RAG 升级时启用 |

## Status Legend

| 状态 | 含义 |
|------|------|
| ✅ 已真实接入 | 代码中真实调用该项目的 CLI/SDK/API，非骨架 |
| ⚠️ 模板理念接入 | 参考了项目的模板理念和结构，但未复制源码或调用其 API |
| 🔶 格式兼容导出 | 生成该工具可直接消费的标准格式文件，但工具本身未安装 |
| 🔶 fallback 自研 | 有自研实现，预留外部项目接入点，当前不依赖外部 |
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

### nuwa-skill / dot-skill (Skill Templates)
- **接入方式**: 参考了 Skill.md 模板理念，自写了中文模板系统
- **实现**: `backend/app/skill_templates/` (base.py, nuwa_style.py, dot_skill_style.py)
- **2026-06 升级**: 新增 `.skill.md` 文件模板，可从文件加载
- **注意**: 本项目未复制 nuwa-skill/dot-skill 源码，实现了兼容的模板层

### mem0 (mem0ai/mem0)
- **接入方式**: Python SDK (`mem0ai`)，可选安装
- **适配器**: `backend/app/integrations/mem0_adapter.py`
- **默认状态**: 关闭 (MEM0_ENABLED=false)
- **Fallback**: SQLite chat_messages
- **依赖**: `pip install mem0ai` (用户手动)

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
3. **mem0** — Long-term memory (install: `pip install mem0ai`, set `MEM0_ENABLED=true`)

### Format-Compatible Export (No Install Needed)
4. **Easy Dataset** — RAG dataset JSONL export
5. **LLaMA Factory** — SFT training data JSONL export

### Template-Inspired (Own Implementation)
6. **nuwa-skill / dot-skill** — Skill.md template system

### Not Yet Running
7. **Chroma / Qdrant** — Vector database (reserved for future RAG upgrade)
8. **LLaMA Factory training** — Actual fine-tuning (requires GPU, out of scope)
