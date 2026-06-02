import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getMineruStatus, getMem0Status, getConfigStatus, type MineruStatus, type Mem0Status, type ConfigStatus } from '../api/client'

type StackStatus = 'enabled' | 'installed_disabled' | 'not_installed' | 'export_only' | 'planned'

interface StackItem {
  name: string
  project: string
  status: StackStatus
  desc: string
}

function statusLabel(s: StackStatus): string {
  const map: Record<StackStatus, string> = {
    enabled: '已启用',
    installed_disabled: '已安装未启用',
    not_installed: '未安装',
    export_only: '仅导出支持',
    planned: '后续计划',
  }
  return map[s]
}

function statusClass(s: StackStatus): string {
  const map: Record<StackStatus, string> = {
    enabled: 'badge badge-success',
    installed_disabled: 'badge badge-warning',
    not_installed: 'badge badge-muted',
    export_only: 'badge badge-info',
    planned: 'badge badge-muted',
  }
  return map[s]
}

export default function HomePage() {
  const [mineru, setMineru] = useState<MineruStatus | null>(null)
  const [mem0, setMem0] = useState<Mem0Status | null>(null)
  const [config, setConfig] = useState<ConfigStatus | null>(null)

  useEffect(() => {
    getMineruStatus().then(setMineru).catch(() => {})
    getMem0Status().then(setMem0).catch(() => {})
    getConfigStatus().then(setConfig).catch(() => {})
  }, [])

  const stackItems: StackItem[] = [
    {
      name: 'DeepSeek',
      project: 'DeepSeek API',
      status: config && !config.is_mock ? 'enabled' : 'not_installed',
      desc: '大模型分析与对话 — deepseek-v4-pro',
    },
    {
      name: 'MinerU',
      project: 'opendatalab/MinerU',
      status: mineru?.installed && mineru?.enabled ? 'enabled'
        : mineru?.installed ? 'installed_disabled' : 'not_installed',
      desc: `PDF/Office/图片解析 — ${mineru?.backend || 'pipeline'} · ${mineru?.method || 'auto'}`,
    },
    {
      name: 'Skill Templates',
      project: 'nuwa-skill / dot-skill',
      status: 'enabled',
      desc: '风格人物蒸馏模板 — 中文自写 Skill.md 兼容模板',
    },
    {
      name: 'mem0',
      project: 'mem0ai/mem0',
      status: mem0?.installed && mem0?.enabled ? 'enabled'
        : mem0?.installed ? 'installed_disabled' : 'not_installed',
      desc: '长期记忆层 — 可选，未安装时使用 SQLite',
    },
    {
      name: 'Easy Dataset',
      project: 'Easy Dataset',
      status: 'export_only',
      desc: 'RAG 数据集 JSONL 导出 — 无需安装原项目',
    },
    {
      name: 'LLaMA Factory',
      project: 'LLaMA Factory',
      status: 'export_only',
      desc: 'SFT 微调数据 JSONL 导出 — 训练需 GPU，不在此项目运行',
    },
  ]

  return (
    <div>
      <div className="card" style={{ marginBottom: '1.5rem', textAlign: 'center', padding: '3rem 2rem' }}>
        <h1 style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>
          AI Clone
        </h1>
        <p style={{ fontSize: '1.1rem', color: 'var(--c-text-muted)', maxWidth: 600, margin: '0 auto 1.5rem' }}>
          GitHub 开源项目聚合型 AI Clone 平台 — 上传资料，生成画像，对话回溯
        </p>
        <p style={{ marginBottom: '1.5rem', lineHeight: 1.8, maxWidth: 700, margin: '0 auto 1.5rem' }}>
          上传某个人的文章、聊天记录、访谈文本、笔记等资料，
          系统自动生成人物画像报告、说话风格卡、记忆时间线，
          并提供一个基于资料检索增强的对话机器人。
        </p>
        <Link to="/profiles" className="btn-primary" style={{ display: 'inline-block', padding: '0.75rem 2rem', fontSize: '1rem' }}>
          开始使用
        </Link>
      </div>

      <div className="disclaimer" style={{ marginBottom: '1.5rem', fontSize: '0.85rem' }}>
        <strong>重要声明：</strong>本产品基于用户提供的资料由 AI 生成模拟角色，
        并非本人意识，不代表本人真实意愿。禁止用于冒充真人、诈骗、骚扰或任何违法用途。
        涉及他人隐私资料时，请确保已获得合法授权。
        如用户要求 AI 冒充真人联系他人、生成欺骗性内容、伪造授权、伪造遗嘱或做出法律/医疗/财务决定，
        系统将拒绝并说明边界。
      </div>

      {/* Open Source Capability Stack */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1rem', marginBottom: '0.75rem', borderBottom: '1px solid var(--c-border)', paddingBottom: '0.5rem' }}>
          开源能力栈
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '0.5rem' }}>
          {stackItems.map(item => (
            <div key={item.name} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '0.5rem 0.75rem', background: 'var(--c-bg-raised)', borderRadius: '6px',
              border: '1px solid var(--c-border)',
            }}>
              <div>
                <strong style={{ fontSize: '0.9rem' }}>{item.name}</strong>
                <div style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)' }}>{item.desc}</div>
              </div>
              <span className={statusClass(item.status)} style={{ fontSize: '0.7rem', whiteSpace: 'nowrap' }}>
                {statusLabel(item.status)}
              </span>
            </div>
          ))}
        </div>
        <p style={{ fontSize: '0.7rem', color: 'var(--c-text-muted)', marginTop: '0.5rem' }}>
          状态说明：已启用 = 真实接入并可运行 | 已安装未启用 = 已安装但配置关闭 | 未安装 = 可选依赖需手动安装 | 仅导出支持 = 生成标准格式文件，不需要安装原项目
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
        <FeatureCard
          title="人物档案管理"
          desc="创建和管理多个人物档案，记录基本信息和关系类型。"
          icon="📋"
        />
        <FeatureCard
          title="智能资料解析"
          desc="支持 txt、md、json、csv、PDF、DOCX、PPTX、XLSX、图片，通过 MinerU 自动解析为可检索文本。"
          icon="📄"
        />
        <FeatureCard
          title="AI 人物画像"
          desc="基于上传资料自动生成详细的人物画像报告和风格卡，包括常用表达、情绪倾向、价值观等。"
          icon="🎯"
        />
        <FeatureCard
          title="RAG 记忆对话"
          desc="基于资料检索增强的对话机器人，以模拟角色方式回答，可选 mem0 长期记忆层。"
          icon="💬"
        />
        <FeatureCard
          title="多 Provider 支持"
          desc="支持 DeepSeek API，也可在 Mock 模式下无 API Key 体验。"
          icon="🔌"
        />
        <FeatureCard
          title="隐私与合规"
          desc="所有数据本地存储，明确的合规边界设计，AI 不会冒充真人或做出违法建议。"
          icon="🔒"
        />
      </div>
    </div>
  )
}

function FeatureCard({ title, desc, icon }: { title: string; desc: string; icon: string }) {
  return (
    <div className="card" style={{ textAlign: 'center' }}>
      <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>{icon}</div>
      <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem' }}>{title}</h3>
      <p style={{ fontSize: '0.85rem', color: 'var(--c-text-muted)' }}>{desc}</p>
    </div>
  )
}
