# AI Clone MVP

AI 人物风格档案 / AI 记忆对话库 — 基于用户提供的资料，自动生成人物画像报告、说话风格卡，并提供基于检索增强的对话机器人。

## 重要声明

- 本产品基于用户提供的资料由 AI 生成模拟角色，**并非本人意识，不代表本人真实意愿**
- **禁止**用于冒充真人、诈骗、骚扰、伪造授权或任何违法用途
- 涉及他人隐私资料时，请确保已获得**合法授权**
- 对话机器人会拒绝冒充真人、生成欺骗性内容、伪造遗嘱、做出法律/医疗/财务决定等请求

## MVP 功能

### 已完成

1. **人物档案管理** — 创建、查看人物档案（姓名、描述、关系类型：亲人/朋友/同事/伴侣/公众人物/作者等）
2. **资料上传与处理** — 支持 txt / md / json / csv / pdf / docx / pptx / xlsx / png / jpg / webp，自动文本清洗、分片、去重
3. **本地轻量检索** — 纯 Python n-gram / 关键词重叠评分检索，SQLite chunks 表存储，零外部依赖
4. **AI 人物画像** — 调用 LLM 生成中文 Markdown 人物画像报告（思维模型、表达DNA、情绪倾向、价值观、可模拟程度评估、合规边界）
5. **AI 风格卡** — 生成结构化风格卡（角色定位、认知方式、表达风格、决策习惯、情绪模式、回答边界、Prompt 使用建议）
6. **RAG 对话** — 本地检索 + 风格卡 + skill template system prompt → 模拟角色对话，聊天回复为自然语言（非 JSON）
7. **DeepSeek 真实接入** — 支持 DeepSeek API（OpenAI-compatible），分析模型和聊天模型可分别配置
8. **MinerU 真实接入** — 支持 PDF、图片、DOCX、PPTX、XLSX 复杂文档解析为 Markdown，再进入 RAG 和画像分析
9. **Skill 模板系统** — 借鉴 nuwa-skill / dot-skill 设计理念，根据关系类型自动选择分析模板（公众人物用 nuwa_style，关系型人物用 dot_skill_style）
10. **Mock 模式** — 无 API Key 时可跑通完整演示流程
11. **导出功能** — 导出 Skill Card（Markdown）和 Dataset（JSONL），兼容 LLaMA Factory / Easy Dataset
12. **合规边界** — 前端声明 + System Prompt + 违规请求拒绝三重保障

### 后续升级方向

- 接入 ChromaDB / Qdrant / FAISS 做向量语义检索
- 接入 Easy Dataset 完整版做数据集制作
- 接入 LLaMA Factory 做 LoRA/QLoRA 微调
- 接入 mem0 做长期记忆
- 语音克隆（需额外授权）
- 多语言支持

详见 [docs/integrations.md](docs/integrations.md)

## 技术栈

| 层 | 技术 |
|---|------|
| 后端框架 | FastAPI (Python) |
| 数据库 | SQLite + SQLAlchemy |
| 检索方式 | 纯 Python n-gram / 关键词重叠评分（轻量本地检索） |
| 前端 | React 18 + Vite + TypeScript + React Router |
| LLM 调用 | 统一抽象层，支持 OpenAI-compatible API |

## 检索说明（第一版）

第一版默认使用 **轻量本地检索**，不依赖任何外部向量数据库：

- 上传文本 → 清洗 → 分片（800 字 + 100 字重叠）→ SHA256 去重 → 存入 SQLite chunks 表
- 检索时：对用户问题做中文字符 unigram/bigram 分词 + 英文单词提取，对每个 chunk 做相同的 tokenize，使用 Jaccard 加权重叠系数打分，返回 top-5 相关片段
- 优点：零外部依赖，安装即用，无需 C++ 编译工具
- 后续可无缝升级到 ChromaDB / Qdrant / FAISS 做语义向量检索

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
│       │   └── profile_service.py     # 画像分析、RAG 对话
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

## API 说明

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/profiles` | 创建人物档案 |
| `GET` | `/api/profiles` | 获取档案列表 |
| `GET` | `/api/profiles/{id}` | 获取档案详情（含最新分析和风格卡） |
| `POST` | `/api/profiles/{id}/documents` | 上传资料文件（multipart/form-data） |
| `GET` | `/api/profiles/{id}/documents` | 查看已上传资料列表 |
| `POST` | `/api/profiles/{id}/analyze` | 生成人物画像和风格卡 |
| `GET` | `/api/profiles/{id}/analysis` | 查看历史分析报告 |
| `POST` | `/api/profiles/{id}/chat` | 发送对话消息（RAG） |
| `GET` | `/api/profiles/{id}/chat` | 查看对话历史 |
| `GET` | `/api/config/status` | LLM Provider 状态（不返回 API Key） |
| `GET` | `/api/integrations/mineru/status` | MinerU 安装与启用状态 |
| `GET` | `/profiles/{id}/export/skill-card` | 导出 Skill Card (Markdown) |
| `GET` | `/profiles/{id}/export/dataset` | 导出 Dataset (JSONL) |
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
- 第一版使用轻量本地检索（纯 Python n-gram），不依赖 ChromaDB/Qdrant/FAISS 等向量数据库
- 升级到向量检索时将增加 Embedding Provider 配置（OpenAI-compatible API）
- 前端使用 React + Vite 全家桶，均为 MIT 协议
- 详见 [docs/integrations.md](docs/integrations.md) 了解各外部项目的集成状态
