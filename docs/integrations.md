# AI Clone — 外部项目集成规划

本文档说明 AI Clone MVP 与各 GitHub 项目的关系，以及当前接入状态。

## 当前已接入

### DeepSeek

- **状态**：已接入（可生产使用）
- **用途**：画像分析 + 聊天回复生成
- **接入方式**：OpenAI-compatible API (`/chat/completions`)
- **配置**：在 `.env` 中设置 `LLM_PROVIDER=deepseek`、`LLM_API_KEY`、`ANALYSIS_MODEL`、`CHAT_MODEL`
- **模型建议**：分析用 `deepseek-chat`，聊天用 `deepseek-chat`
- **注意**：DeepSeek API 兼容 OpenAI SDK，无需额外依赖

### Mock Provider

- **状态**：已内置
- **用途**：无 API Key 时的演示和开发调试
- **切换**：`LLM_PROVIDER=mock` 或不填 `LLM_API_KEY`

---

## 以模板/适配器形式接入的 GitHub 项目

以下项目**没有直接复制代码**，而是根据其设计理念实现了可插拔的模板层或适配器骨架。

### nuwa-skill

- **GitHub**：https://github.com/astra-version/nuwa-skill (待确认)
- **借鉴理念**：
  - 提取公众人物/作者/思想者的 mental models（思维模型）
  - 提取 decision heuristics（决策启发式）
  - 提取 expression DNA（表达特征）
  - 定义 value boundaries（价值边界）
- **本项目实现**：`backend/app/skill_templates/nuwa_style.py`
  - 适用于 `public_figure`、`author`、`celebrity` 关系类型
  - 画像分析 prompt 包含思维模型、决策启发式、表达 DNA 三个维度
  - 风格卡提示包含可模拟程度评估
  - **未直接复制 nuwa-skill 仓库代码**
- **后续完整集成**（需确认许可证后）：
  - nuwa-skill 的 agent skill 生成逻辑
  - nuwa-skill 的 evolution system
  - nuwa-skill 的 three-world-collision 机制

### dot-skill / colleague-skill

- **GitHub**：https://github.com/astra-version/dot-skill (待确认)
- **借鉴理念**：
  - 按关系类型分类人物模拟（colleague、relationship、celebrity）
  - 三类对象的分析维度不同
  - 关系型人物强调互动特征和沟通模式
- **本项目实现**：`backend/app/skill_templates/dot_skill_style.py`
  - 适用于 `colleague`、`friend`、`family`、`lover`、`other` 关系类型
  - 画像分析包含关系互动特征、沟通风格、冲突处理
  - **未直接复制 dot-skill 仓库代码**
- **后续完整集成**（需确认许可证后）：
  - dot-skill 的 skill 自定义逻辑
  - dot-skill 的多角色管理
  - dot-skill 的 memory 系统

---

## 可选依赖（已接入，未安装时不影响核心功能）

以下项目的适配器已创建。**未安装对应依赖时不影响项目启动和核心功能**，调用时返回清晰错误提示。

### MinerU (真实接入)

- **适配器**：`backend/app/integrations/mineru_adapter.py`
- **GitHub**：https://github.com/opendatalab/MinerU
- **用途**：PDF、图片、DOCX、PPTX、XLSX → Markdown/JSON 转换
- **状态**：已真实接入，可选依赖
- **如何启用**：
  ```bash
  # Windows — 一键安装
  powershell -ExecutionPolicy Bypass -File scripts/install_mineru_windows.ps1
  
  # 重启后端后检查状态
  curl http://localhost:8000/api/integrations/mineru/status
  ```
- **启用后**：上传 PDF/DOCX/PPTX/XLSX/PNG/JPG 等即可自动转 Markdown，再进入 RAG 和画像分析
- **未安装时**：txt/md/json/csv 上传不受影响；复杂文档上传会返回 400 并提示安装步骤
- **注意**：MinerU 只负责解析文档，人格分析仍由 DeepSeek 完成

### Easy Dataset

- **适配器**：`backend/app/integrations/easy_dataset_adapter.py`
- **GitHub**：https://github.com/ConardLi/easy-dataset (待确认)
- **用途**：把资料加工成微调/RAG/Eval 数据集
- **MVP 已提供**：`GET /api/profiles/{id}/export/dataset` 导出 chunks 为 JSONL
- **当前可导出**：Chunks + Chat Messages + Analysis → JSONL 格式
- **如何启用完整功能**（后续）：
  ```bash
  pip install easy-dataset
  ```

### LLaMA Factory

- **适配器**：`backend/app/integrations/llamafactory_adapter.py`
- **GitHub**：https://github.com/hiyouga/LLaMA-Factory
- **用途**：LoRA/QLoRA 微调大模型，让角色模拟更精准
- **MVP 已提供**：`export_sft_dataset()` 导出 SFT 训练数据为 LLaMA Factory 兼容的 JSONL
- **依赖**：需要 PyTorch + transformers + LLaMA Factory（重依赖，不在 MVP 范围）
- **暂不启用原因**：需要 GPU、训练时间、模型部署，远超 MVP 范围

### mem0

- **适配器**：`backend/app/integrations/mem0_adapter.py`
- **GitHub**：https://github.com/mem0ai/mem0
- **用途**：长期记忆、跨会话偏好、用户画像更新
- **MVP 替代**：SQLite `chat_messages` 表提供当前会话内上下文
- **如何启用**（后续）：
  ```bash
  pip install mem0ai
  # 配置 MEM0_ENABLED=true
  ```

---

## 架构原则

1. **可插拔**：每个外部项目通过适配器接入，不硬编码到核心逻辑
2. **渐进增强**：MVP 用最简单方式实现（SQLite chunks、n-gram 检索、Mock LLM），生产环境逐步替换
3. **许可证安全**：不以任何方式复制外部仓库代码，只实现兼容其设计理念的模板/适配器
4. **启动不崩溃**：未安装的依赖不影响项目启动，调用时给出清晰错误提示

## 当前技术栈数据流

```
上传文件 (.txt/.md/.json/.csv/.pdf/.docx/.pptx/.xlsx/.png/.jpg/.webp)
  → (复杂文档) MinerU 解析 → Markdown
  → document_processor.py (clean → chunk → dedup)
  → SQLite chunks 表
  → (可选) 画像分析：LLM (DeepSeek/Mock) + skill_templates
  → (可选) 聊天 RAG：search_chunks_local + LLM + 风格卡
  → 前端展示：画像报告 / 风格卡 / 对话气泡
```

## 升级路径

| 阶段 | 新增内容 |
|------|---------|
| 当前 MVP | DeepSeek API + Mock + MinerU + skill templates |
| 第二阶段 | ChromaDB (向量检索) + 改进 RAG |
| 第三阶段 | Easy Dataset 完整版 + LLaMA Factory (微调) |
| 第四阶段 | mem0 (长期记忆) + 语音克隆 (需授权) |
