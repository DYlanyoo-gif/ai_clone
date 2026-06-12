# AI Clone — 基于资料证据的深度人物分析系统

基于用户提供的资料，通过 **资料解析 → 证据提取 → 深度画像 → 风格卡 → 分析报告导出** 的完整流水线，自动生成带证据链的人物分析报告。对话机器人基于风格卡和资料检索提供模拟角色对话。

## 产品主线

资料解析（MinerU）→ 证据提取（DeepSeek）→ 深度画像（14 模块 + evidence_map）→ 风格卡（10 章节）→ 分析报告导出

mem0 长期记忆为**可选功能**，已默认关闭。当前产品方向以"AI Clone 深度人物分析"为核心，不以长期记忆为主线。

## 重要声明

- 本产品基于用户提供的资料由 AI 生成模拟角色，**并非本人意识，不代表本人真实意愿**
- **禁止**用于冒充真人、诈骗、骚扰、伪造授权或任何违法用途
- 涉及他人隐私资料时，请确保已获得**合法授权**
- 对话机器人会拒绝冒充真人、生成欺骗性内容、伪造遗嘱、做出法律/医疗/财务决定等请求
- 分析结果附证据链，资料不足时标注"资料不足"，不无证据下结论
- 不做医学或精神疾病诊断，不把推测写成事实

## 开源能力栈

本项目定位为 **GitHub 开源项目聚合型 AI Clone 平台**，尽量接入成熟开源项目，自己只写 glue code。

| 能力模块 | 开源项目 | 接入状态 | 说明 |
|---------|---------|---------|------|
| 大模型分析 & 报告生成 | [DeepSeek](https://api.deepseek.com) | ✅ 真实接入 | 14 模块画像 + 证据地图 + 分析报告 |
| 文档解析 | [opendatalab/MinerU](https://github.com/opendatalab/MinerU) | ✅ 真实接入 | PDF/Office/图片 → Markdown |
| Persona Skill Foundry | [nuwa-skill](https://github.com/alchaincyf/nuwa-skill) / [colleague-skill](https://github.com/titanwings/colleague-skill) | 🔧 external submodule + 兼容包生成 + Website Runtime | 读取外部契约，生成 Nuwa / dot-skill compatible package，并可站内运行测试 |
| 长期记忆 | [mem0ai/mem0](https://github.com/mem0ai/mem0) | 🔧 可选接入 | **非主线**，默认关闭，SQLite 为 fallback |
| 数据集导出 | [Easy Dataset](https://github.com/ConardLi/easy-dataset) | 🔶 格式兼容导出 | 标准 JSONL + evidence metadata |
| 微调数据导出 | [LLaMA Factory](https://github.com/hiyouga/LLaMA-Factory) | 🔶 格式兼容导出 | 含证据样本的 SFT 数据，不训练 |
| RAG 检索 | Qdrant + FastEmbed / 自研 n-gram | 🔧 可选接入 + fallback | 默认关键词检索，启用后优先语义检索 |
| 向量检索 | Qdrant local on-disk / FastEmbed | 🔧 可选接入 | 见 docs/vector_retrieval_plan.md |

详细审计见 [docs/open_source_integration_audit.md](docs/open_source_integration_audit.md)

## MVP 功能

### 已完成

1. **人物档案管理** — 创建、查看人物档案（姓名、描述、关系类型：亲人/朋友/同事/伴侣/公众人物/作者等）
2. **资料上传与处理** — 支持 txt / md / json / csv / pdf / docx / pptx / xlsx / png / jpg / webp，自动文本清洗、分片、去重
3. **资料管理** — 删除文档（含确认弹窗）、预览解析文本（前 3000 字）、重建文本片段
4. **本地轻量检索** — 纯 Python n-gram / 关键词重叠评分检索，SQLite chunks 表存储，零外部依赖
5. **AI 人物画像** — 调用 LLM 生成中文 Markdown 人物画像报告（14 模块深度分析）
6. **AI 风格卡** — 生成结构化可执行风格卡（10 章节），可被 Claude Code / Codex / Cursor 直接读取
7. **RAG 对话** — 本地检索 + 风格卡 + skill template system prompt → 模拟角色对话，6 种聊天模式
8. **DeepSeek 真实接入** — 支持 DeepSeek API（OpenAI-compatible），分析模型和聊天模型可分别配置
9. **MinerU 真实接入** — 支持 PDF、DOCX、PPTX、XLSX、图片解析为 Markdown（可配 backend/method/lang）
10. **Persona Skill Foundry** — 已导入 nuwa-skill / colleague-skill 到 `external/`，可基于证据画像生成兼容 Skill 包并下载 ZIP
11. **Website-native Skill Runtime** — 在网站内用当前 LLM Provider 读取 Nuwa / Colleague Skill 包运行测试，支持 Compare、证据检查、不确定性检查和反馈记录
12. **mem0 长期记忆（可选）** — 安装 `pip install mem0ai` 并设置 `MEM0_ENABLED=true` 后启用，未安装时使用 SQLite
13. **Mock 模式** — 无 API Key 时可跑通完整演示流程
14. **导出功能** — Skill Card（SKILL.md）、RAG Dataset（JSONL）、LLaMA Factory SFT（JSONL）三种导出
15. **开源能力栈展示** — 首页显示各开源项目的接入状态（已启用/未安装/仅导出支持）
16. **合规边界** — 前端声明 + System Prompt + 违规请求拒绝三重保障

### 后续升级方向

- 扩展更多向量检索 provider（当前已支持可选 Qdrant local + FastEmbed）
- 实际运行 LLaMA Factory 训练（当前仅导出数据）
- 语音克隆（需额外授权）

## 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | FastAPI (Python) |
| 数据库 | SQLite + SQLAlchemy |
| 检索方式 | Qdrant + FastEmbed（可选）/ 纯 Python n-gram fallback |
| 前端 | React 18 + Vite + TypeScript + React Router |
| LLM 调用 | 统一抽象层，支持 OpenAI-compatible API |

## 检索说明

默认使用 **轻量本地关键词检索**，不依赖任何外部向量数据库：

- 上传文本 → 清洗 → 分片（800 字 + 100 字重叠）→ SHA256 去重 → 存入 SQLite chunks 表
- 检索时：对用户问题做中文字符 unigram/bigram 分词 + 英文单词提取，对每个 chunk 做相同的 tokenize，使用 Jaccard 加权重叠系数打分，返回 top-5 相关片段
- 优点：零外部依赖，安装即用，无需 C++ 编译工具
- 可选升级：安装 `qdrant-client fastembed` 并设置 `VECTOR_ENABLED=true` 后，系统会优先使用 Qdrant local on-disk + FastEmbed 做语义证据检索；不可用时自动回退关键词检索。

## 项目结构

```
ai_clone/
├── backend/
│   └── app/
│       ├── api/routes.py              # FastAPI 路由
│       ├── core/config.py             # 配置管理（.env）
│       ├── models/
│       │   ├── database.py            # SQLAlchemy 表定义
│       │   └── session.py             # 数据库连接管理
│       ├── schemas/models.py          # Pydantic 请求/响应模型
│       ├── services/
│       │   ├── llm_provider.py        # LLM 抽象层（Mock + OpenAI-compatible）
│       │   ├── document_processor.py  # 文本清洗、分片、轻量检索
│       │   ├── profile_service.py     # 画像分析、RAG 对话
│       │   └── skill_runtime_service.py # Website-native Skill Runtime
│       └── main.py                    # FastAPI 入口
├── frontend/
│   ├── src/
│   │   ├── api/client.ts              # API 客户端
│   │   ├── components/Layout.tsx      # 全局布局
│   │   ├── pages/
│   │   │   ├── HomePage.tsx           # 首页
│   │   │   ├── ProfileListPage.tsx    # 人物列表
│   │   │   ├── ProfileDetailPage.tsx  # 人物详情 + 资料管理
│   │   │   └── ChatPage.tsx           # 对话窗口
│   │   ├── styles/global.css          # 全局样式
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── data/                              # SQLite + 上传文件
├── docs/                              # 产品设计文档
├── .env.example                       # 环境变量模板
├── requirements.txt                   # Python 依赖
├── start_backend.bat                  # 后端启动脚本
├── start_frontend.bat                 # 前端启动脚本
└── README.md
```

## 快速开始

### 前置要求

- Python 3.10+
- Node.js 18+
- （可选）DeepSeek API Key 或 OpenAI API Key

### 1. 进入目录

```bash
cd ai_clone
```

### 2. 启动后端

```bash
# Windows — 一键启动
start_backend.bat

# 或手动执行
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r ..\requirements.txt
copy ..\.env.example ..\.env
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

后端启动后访问 http://localhost:8000/docs 查看 API 文档。

### 3. 启动前端

```bash
# Windows
start_frontend.bat

# 或手动执行
cd frontend
npm install
npm run dev
```

前端启动后访问 http://localhost:5173。

## Production Deployment

生产环境请使用域名访问，不要把 Vite 开发端口 `5173` 暴露给用户。推荐部署方式：

- `npm run build` 生成 `frontend/dist`
- Nginx 托管 `frontend/dist`
- Nginx 将 `/api` 反向代理到 FastAPI `127.0.0.1:8000`
- FastAPI 后端由 systemd 常驻运行
- DeepSeek API Key 只放在 VPS 的 `/opt/ai_clone/.env`，不要提交到 GitHub
- 简历展示或公开 demo 建议开启 Nginx Basic Auth，避免陌生访问消耗 API 额度

部署模板已放在：

- [deploy/nginx.conf.example](deploy/nginx.conf.example)
- [deploy/systemd-backend.service.example](deploy/systemd-backend.service.example)
- [.env.production.example](.env.production.example)
- [deploy/README_DEPLOY.md](deploy/README_DEPLOY.md)

完整 VPS 部署步骤见 [deploy/README_DEPLOY.md](deploy/README_DEPLOY.md)。本地开发仍使用 `http://localhost:5173`，生产访问应使用你的域名，例如 `https://echo.example.com`。

### 4. 配置 LLM Provider

编辑项目根目录的 `.env` 文件。**默认使用 Mock 模式**（无需 API Key 即可演示）。

#### 使用 DeepSeek（推荐）

```env
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-your-deepseek-api-key
ANALYSIS_MODEL=deepseek-chat
CHAT_MODEL=deepseek-chat
LLM_TIMEOUT_SECONDS=120
```

1. 获取 API Key：注册 https://platform.deepseek.com，在 API Keys 页面创建
2. 复制 `.env.example` 为 `.env`
3. 修改 `LLM_PROVIDER=deepseek`，填入你的 `LLM_API_KEY`
4. 重启后端（`start_backend.bat`）
5. 验证：打开 http://localhost:8000/docs，调用 `GET /api/config/status`，确认 `llm_provider` 为 `deepseek`，`is_mock` 为 `false`

#### 使用 OpenAI

```env
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-openai-api-key
ANALYSIS_MODEL=gpt-4o-mini
CHAT_MODEL=gpt-4o-mini
```

#### 使用 Mock（默认、无需 Key）

```env
LLM_PROVIDER=mock
# 不需要填写 LLM_API_KEY
```

Mock 模式下所有功能可正常演示，LLM 返回预设的模拟内容。

### 5. （可选）安装 MinerU 支持复杂文档解析

MinerU 用于解析 PDF、图片、DOCX、PPTX、XLSX 等复杂文档为 Markdown，再进入 RAG 和画像分析流程。

**安装步骤 (Windows)：**

```bash
cd C:\Projects\ai_clone
powershell -ExecutionPolicy Bypass -File scripts/install_mineru_windows.ps1
```

安装完成后重启后端，打开 http://localhost:8000/api/integrations/mineru/status 检查状态：
- `installed: true` — 安装成功
- `installed: false` — 安装失败，查看 `error` 字段

**不需要 MinerU 时：**
- 跳过安装即可，txt/md/json/csv 上传不受任何影响
- 或在 `.env` 中设置 `MINERU_ENABLED=false` 关闭

**故障处理：**
| 问题 | 可能原因 | 解决 |
|------|---------|------|
| 安装慢 | 下载模型文件较大 | 正常现象，10-30 分钟 |
| 缺少模型文件 | 网络问题下载失败 | 重试安装脚本 |
| PDF 解析为空 | 扫描件/图片质量低 | 使用更清晰的文档或手动转文本 |
| 扫描件识别差 | OCR 依赖模型质量 | 这是已知限制，建议优先使用文本 PDF |
| 路径含中文/空格 | Windows 路径兼容性 | 避免含中文或空格的路径 |

**重要说明：**
- MinerU 只负责文档解析，不负责人格分析；人格分析仍由 DeepSeek 完成
- MinerU 是可选依赖，不影响现有 txt/md/json/csv 上传
- 上传 PDF/docx 等文件时，如果 MinerU 未安装，接口会返回清晰的 400 错误提示

### 6. （可选）安装 mem0 支持长期记忆

mem0 为 AI 对话提供跨会话的长期记忆层，让 AI 记住用户的偏好、历史对话要点等。**不是人物分析模型**，而是记忆存储和检索层。未安装时，系统使用 SQLite chat_messages 表存储短期历史。

**安装步骤：**
```bash
# 1. 安装 mem0ai Python 包
pip install mem0ai

# 2. 编辑 .env 文件，启用 mem0
#    将以下内容加入 .env：
#    MEM0_ENABLED=true
#    MEM0_PROVIDER=local
#    MEM0_COLLECTION_PREFIX=ai_clone_profile

# 3. 重启后端
#    Ctrl+C 停止当前后端，再运行 start_backend.bat
```

**验证安装：**
```bash
# 检查 mem0 状态接口
curl http://localhost:8000/api/integrations/mem0/status
```

预期返回：
```json
{
  "installed": true,
  "enabled": true,
  "available": true,
  "provider": "local",
  "error": null,
  "detail": "mem0 已安装、已启用、API 可用。"
}
```

如果 `available: false`，说明 mem0 API 版本与适配器不兼容。检查 mem0ai 版本：`pip show mem0ai`。

**验收长期记忆：**
1. 聊天时说："我喜欢直接一点的回答，先给结论再展开。"
2. 继续聊天几轮，然后问："你还记得我刚才的偏好是什么吗？"
3. 如果 mem0 已启用且正常，AI 应能提到"直接、先给结论"。
4. 如果 mem0 不可用，AI 不会崩溃，仅基于当前上下文回答。

**说明：**
- 人物分析仍由 DeepSeek 完成
- mem0 调用失败时自动回退到 SQLite，不会导致聊天失败
- 默认关闭（`MEM0_ENABLED=false`），不影响现有功能

### 7. （可选）安装 Qdrant + FastEmbed 支持语义证据检索

向量检索用于提升证据片段命中质量，不替代 SQLite chunks，也不影响 DeepSeek、MinerU 或 mem0。默认关闭，未安装依赖时项目仍正常使用关键词检索 fallback。

**安装依赖：**
```bash
pip install qdrant-client fastembed

# 或使用项目虚拟环境
backend\venv\Scripts\python.exe -m pip install qdrant-client fastembed
```

**启用配置：**
```env
VECTOR_ENABLED=true
VECTOR_PROVIDER=qdrant
VECTOR_EMBEDDING_PROVIDER=fastembed
VECTOR_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
VECTOR_COLLECTION_PREFIX=ai_clone_profile
VECTOR_QDRANT_PATH=../data/qdrant
VECTOR_TOP_K=8
```

重启后端后访问：
```bash
curl http://localhost:8000/api/integrations/vector/status
```

预期 `available: true`。随后在人物详情页点击“重建向量索引”，或调用：
```bash
curl -X POST http://localhost:8000/api/profiles/1/vector/rebuild
curl "http://localhost:8000/api/profiles/1/vector/search?query=写作风格"
```

如果依赖未安装、`VECTOR_ENABLED=false` 或 Qdrant/FastEmbed 初始化失败，系统会自动回退关键词检索，并在状态接口中返回清晰说明。

### 8. Persona Skill Foundry（Nuwa / dot-skill 兼容包）

本项目已将两个开源仓库作为 submodule 导入：

- `external/nuwa-skill` → https://github.com/alchaincyf/nuwa-skill
- `external/colleague-skill` → https://github.com/titanwings/colleague-skill

AI Clone 不自动调用外部仓库的采集器、writer、宿主安装器或不稳定 CLI。原因是本项目已经有自己的资料上传、MinerU 解析、DeepSeek 画像、evidence_map 和导出流程；当前 Foundry 只读取外部仓库的 README / SKILL / prompts 契约，并把现有人物档案生成兼容文件包。

真实接入等级按验证阶段拆分，不把“可下载”直接称为完全 L5：

| 等级 | 含义 |
|------|------|
| L3 repo imported | 外部仓库已导入 `external/` |
| L4 spec parsed + compatible skill generated | 已读取契约并生成兼容包 |
| L5a structure validated | 本地结构验证通过，含 SKILL.md、manifest、证据策略和敏感文件检查 |
| L5b dry-run simulated | 在本项目内用当前 LLM provider 做 dry-run 模拟，`runtime_simulated=true` |
| L5c actual runtime tested | 用户安装到 Codex / Claude Code / Hermes 等外部 runtime 后真实执行测试，并把结果回填 AI Clone 通过评估 |

当前系统可在网站内完成结构验证和 dry-run 模拟。真正外部 runtime 测试需要用户把 Skill 包安装到对应 runtime 的 skills 目录中手动验证；AI Clone 不自动调用 Codex / Claude Code / Hermes，也不会伪造 L5c。

#### Website-native Skill Runtime

人物详情页的 `Skill Runtime Lab` 可以在网站内运行已生成的 Nuwa / Colleague Skill 包。它使用当前配置的 LLM Provider（DeepSeek / OpenAI-compatible / Mock），不访问外部 Codex、Claude Code 或 Hermes runtime。

运行时读取生成目录中的真实 Skill 文件：

- 通用：`SKILL.md`
- Nuwa：`persona.md`、`thinking_framework.md`、`decision_heuristics.md`、`expression_dna.md`、`evidence_map.md`、`source_manifest.json`
- Colleague：`persona.md`、`work.md`、`persona_skill.md`、`work_skill.md`、`evidence_map.md`、`source_manifest.json`

运行模式：

- `nuwa_thinking`：测试人物心智模型、决策启发式与表达 DNA
- `colleague_interaction`：测试协作规则、工作流与互动边界
- `evidence_check`：检查回答是否引用证据、区分事实与推断
- `uncertainty_check`：检查资料不足时是否承认不确定
- `compare`：同时运行 Nuwa 与 Colleague，生成差异表和使用建议

Website Runtime 会把运行记录写入 `skill_runtime_runs`，反馈写入 `skill_runtime_feedback`。当反馈为 `inaccurate`、`not_like_person` 或 `missing_evidence` 时，会追加到对应 Skill 包的 `correction_history.md`，但系统不会自动重写 Skill。

重要边界：Website Runtime 是站内测试，不等于外部真实 runtime。它不会把 Skill 标记为 L5c；L5c 仍然只能来自用户手动安装到外部 runtime 后回填的测试结果。

#### 如何达到 L5c

1. 在人物详情页生成 Nuwa 或 Colleague 兼容 Skill 包。
2. 点击“验证 Skill 包”，通过后为 L5a。
3. 点击“Dry-run”，站内模拟通过后为 L5b。注意：Dry-run 是站内模拟，不等于真实 runtime。
4. 点击“安装说明”，选择目标 runtime，并下载 ZIP。
5. 点击“生成 Runtime 测试用例”，系统会写入：
   - `runtime_test_cases.md`
   - `runtime_test_cases.json`
6. 将 ZIP 解压并安装到 Codex / Claude Code / Hermes / Generic Agent Skill runtime。
7. 在外部 runtime 中按 `runtime_test_cases.md` 逐条运行测试。
8. 回到人物详情页，点击“回填外部运行结果”，粘贴完整输出和测试备注。
9. 点击“评估运行结果”。只有满足硬条件时才标记 L5c：
   - 已选择 runtime_target
   - test_output_text 非空
   - 至少 3 个测试用例有可判断输出
   - Safety boundary test 通过
   - Evidence policy test 通过

L5c 记录会写入 `runtime_validation_results` 表，并在 `generated_skills` 上记录 `l5c_runtime_target`、`l5c_passed`、`l5c_score`、`l5c_result_id`、`l5c_validated_at`。

生成目录：

```text
generated_skills/{profile_slug}/nuwa/
generated_skills/{profile_slug}/colleague/
```

Nuwa-compatible package 包含：

- `SKILL.md`
- `persona.md`
- `thinking_framework.md`
- `decision_heuristics.md`
- `expression_dna.md`
- `evidence_map.md`
- `source_manifest.json`
- `README.md`
- `install_instructions.md`（生成安装说明后）
- `runtime_test_cases.md` / `runtime_test_cases.json`（生成测试用例后）

Dot-skill-compatible package 包含：

- `SKILL.md`
- `persona.md`
- `work.md`
- `persona_skill.md`
- `work_skill.md`
- `meta.json`
- `manifest.json`
- `source_manifest.json`
- `README.md`
- `install_instructions.md`（生成安装说明后）
- `runtime_test_cases.md` / `runtime_test_cases.json`（生成测试用例后）

`source_manifest.json` 只记录文件元数据和证据来源摘要，不打包原始上传文件、数据库、`.env`、API Key 或 Git remote。

### 9. 导出功能说明

三种导出格式：

| 导出类型 | 端点 | 格式 | 用途 |
|---------|------|------|------|
| Skill Card | `GET /api/profiles/{id}/export/skill-card` | SKILL.md Markdown | 可被 Claude Code / Codex / Cursor 读取 |
| RAG Dataset | `GET /api/profiles/{id}/export/dataset` | JSONL | Easy Dataset 兼容的 RAG 数据集 |
| SFT Dataset | `GET /api/profiles/{id}/export/sft` | JSONL (messages) | LLaMA Factory 兼容的微调训练数据 |

**关于 LLaMA Factory：** LLaMA Factory 是后续训练工具，需要 PyTorch + GPU。本项目当前只负责导出可训练的标准格式数据，不在本项目中实际运行训练。详见 [LLaMA Factory](https://github.com/hiyouga/LLaMA-Factory)。

**关于 Skill Templates：** 旧有 `backend/app/skill_templates/templates/` 仍保留为本地画像/聊天模板层。新增 Persona Skill Foundry 使用 `external/nuwa-skill` 与 `external/colleague-skill` 的契约生成兼容包，但不执行外部采集器或宿主安装器。

## API 说明

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/profiles` | 创建人物档案 |
| `GET` | `/api/profiles` | 获取档案列表 |
| `GET` | `/api/profiles/{id}` | 获取档案详情（含最新分析和风格卡） |
| `POST` | `/api/profiles/{id}/documents` | 上传资料文件（multipart/form-data） |
| `GET` | `/api/profiles/{id}/documents` | 查看已上传资料列表 |
| `GET` | `/api/profiles/{id}/documents/{doc_id}/preview` | 预览文档前 3000 字解析文本 |
| `DELETE` | `/api/profiles/{id}/documents/{doc_id}` | 删除文档及对应 chunks |
| `POST` | `/api/profiles/{id}/rebuild-chunks` | 重建所有文档的文本片段 |
| `POST` | `/api/profiles/{id}/analyze` | 生成人物画像和风格卡 |
| `GET` | `/api/profiles/{id}/analysis` | 查看历史分析报告 |
| `POST` | `/api/profiles/{id}/chat` | 发送对话消息（RAG + mem0） |
| `GET` | `/api/profiles/{id}/chat` | 查看对话历史 |
| `GET` | `/api/integrations/vector/status` | 向量检索安装、启用与 collection 状态 |
| `POST` | `/api/profiles/{id}/vector/rebuild` | 用现有 chunks 重建 Qdrant 向量索引 |
| `GET` | `/api/profiles/{id}/vector/search?query=` | 语义检索测试（不可用时 fallback） |
| `POST` | `/api/profiles/{id}/memory/rebuild` | 重建 mem0 长期记忆（需先安装 mem0） |
| `GET` | `/api/profiles/{id}/memory/search?q=` | 搜索 mem0 长期记忆 |
| `GET` | `/api/config/status` | LLM Provider 状态（不返回 API Key） |
| `GET` | `/api/integrations/mineru/status` | MinerU 安装、配置与启用状态 |
| `GET` | `/api/integrations/mem0/status` | mem0 安装与启用状态 |
| `GET` | `/api/integrations/vector/status` | Qdrant/FastEmbed 向量检索状态 |
| `GET` | `/api/integrations/nuwa/status` | Nuwa 仓库导入与接入层级 |
| `GET` | `/api/integrations/nuwa/spec` | Nuwa Skill 契约摘要 |
| `GET` | `/api/integrations/colleague/status` | colleague/dot-skill 仓库导入与接入层级 |
| `GET` | `/api/integrations/colleague/spec` | colleague/dot-skill 契约摘要 |
| `GET` | `/api/profiles/{id}/skills` | 查看该人物已生成 Skill 包 |
| `POST` | `/api/profiles/{id}/skills/nuwa/generate` | 生成 Nuwa-compatible package |
| `POST` | `/api/profiles/{id}/skills/colleague/generate` | 生成 dot-skill-compatible package |
| `POST` | `/api/profiles/{id}/skills/{skill_id}/validate` | 验证 Skill 包结构、manifest 与敏感文件 |
| `POST` | `/api/profiles/{id}/skills/{skill_id}/dry-run` | 使用当前 LLM provider 做本地 dry-run 模拟 |
| `GET` | `/api/profiles/{id}/skills/{skill_id}/validation` | 获取最近一次验证状态 |
| `GET` | `/api/profiles/{id}/skills/{skill_id}/install-instructions?target=codex` | 生成安装说明文件 |
| `POST` | `/api/profiles/{id}/skills/{skill_id}/runtime-testcases` | 生成外部 runtime 测试用例 |
| `GET` | `/api/profiles/{id}/skills/{skill_id}/runtime-testcases` | 查看外部 runtime 测试用例 |
| `POST` | `/api/profiles/{id}/skills/{skill_id}/runtime-results` | 回填外部 runtime 运行结果 |
| `GET` | `/api/profiles/{id}/skills/{skill_id}/runtime-results` | 查看历史外部 runtime 回填记录 |
| `POST` | `/api/profiles/{id}/skills/{skill_id}/runtime-results/evaluate` | 评估回填结果，满足条件后记录 L5c |
| `POST` | `/api/profiles/{id}/skills/{skill_id}/run` | Website Runtime 站内运行单个 Skill |
| `GET` | `/api/profiles/{id}/skills/{skill_id}/runs` | 查看 Website Runtime 运行记录 |
| `GET` | `/api/profiles/{id}/skills/{skill_id}/runs/{run_id}` | 查看单次 Website Runtime 运行详情 |
| `POST` | `/api/profiles/{id}/skills/compare-run` | Nuwa / Colleague 站内对照运行 |
| `POST` | `/api/profiles/{id}/skills/{skill_id}/runs/{run_id}/feedback` | 回填站内运行反馈，不自动重写 Skill |
| `GET` | `/api/profiles/{id}/skills/{skill_id}/download` | 下载生成的 Skill ZIP |
| `GET` | `/api/profiles/{id}/export/skill-card` | 导出 Skill Card (SKILL.md) |
| `GET` | `/api/profiles/{id}/export/dataset` | 导出 RAG Dataset (JSONL) |
| `GET` | `/api/profiles/{id}/export/sft` | 导出 LLaMA Factory SFT (JSONL) |
| `GET` | `/api/health` | 健康检查 |

### 请求/响应示例

```bash
# 创建人物
curl -X POST http://localhost:8000/api/profiles \
  -H "Content-Type: application/json" \
  -d '{"name": "张三", "description": "一位作家", "relationship_type": "friend"}'

# 上传资料
curl -X POST http://localhost:8000/api/profiles/1/documents \
  -F "file=@articles.txt"

# 生成分析
curl -X POST http://localhost:8000/api/profiles/1/analyze

# 对话
curl -X POST http://localhost:8000/api/profiles/1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "你对写作有什么看法？"}'
```

## 数据库表结构

| 表名 | 说明 |
|------|------|
| `profiles` | 人物档案 |
| `documents` | 上传的文档记录 |
| `chunks` | 文本片段（本地检索知识库） |
| `analysis_reports` | 分析报告（画像 + 风格卡） |
| `chat_messages` | 对话历史 |
| `generated_skills` | Persona Skill Foundry 生成包、L5a/L5b/L5c 状态 |
| `runtime_validation_results` | 外部 runtime 测试结果回填与 L5c 审计记录 |
| `skill_runtime_runs` | Website-native Skill Runtime 站内运行记录 |
| `skill_runtime_feedback` | 站内运行反馈与 correction_history 线索 |

## 合规与边界设计

### 前端

- 首页和对话页均有醒目的合规声明
- 说明产品定位：AI 模拟角色，非本人意识

### 后端 System Prompt

- 角色定位：AI 模拟角色，不声称是真人
- 禁答边界：冒充真人、欺骗、伪造授权、遗嘱、法律/医疗/财务决定
- 资料不足时明确告知用户
- 对话机器人的拒绝机制嵌入 system prompt

## Mock 模式说明

当 `LLM_PROVIDER=mock` 或未配置 API Key 时：

- LLM 调用返回预设的模拟分析结果
- 检索使用本地 n-gram 关键词评分，纯 Python 实现，无需额外依赖
- 前端全部流程可正常跑通，便于开发调试和演示

## Skill 模板系统

人物画像分析和对话风格由 **Skill 模板** 决定。模板根据关系类型自动选择：

| 关系类型 | 模板 | 分析重点 |
|---------|------|---------|
| `public_figure` / `author` / `celebrity` | nuwa_style | 思维模型、决策启发式、表达DNA、价值边界 |
| `colleague` / `friend` / `family` / `lover` | dot_skill_style | 互动特征、沟通风格、冲突处理、情绪表达 |

模板位于 `backend/app/skill_templates/`：
- `base.py` — 模板数据结构与注册机制
- `nuwa_style.py` — 公众人物/作者/思想家模板
- `dot_skill_style.py` — 关系型人物模板

本项目**未直接复制** nuwa-skill / dot-skill 仓库代码，而是实现了兼容其设计理念的独立模板层。

## License

本项目代码仅供学习和研究使用。其中 LLM 调用依赖外部服务，请遵守各服务商的使用条款。

## 注意事项

- 本项目的风格卡设计借鉴了 nuwa-skill / dot-skill 的产品思路（提炼认知方式、表达风格、决策习惯、边界），但**未直接复制其代码**
- 默认使用轻量本地检索（纯 Python n-gram），不依赖 ChromaDB/Qdrant/FAISS 等向量数据库
- 可选向量检索已支持 Qdrant local on-disk + FastEmbed；默认关闭，失败时 fallback 到关键词检索
- 前端使用 React + Vite 全家桶，均为 MIT 协议
- 详见 [docs/integrations.md](docs/integrations.md) 了解各外部项目的集成状态
