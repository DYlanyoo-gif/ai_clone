import { Link } from 'react-router-dom'

export default function HomePage() {
  return (
    <div>
      <div className="card" style={{ marginBottom: '1.5rem', textAlign: 'center', padding: '3rem 2rem' }}>
        <h1 style={{ fontSize: '2rem', marginBottom: '0.75rem' }}>
          AI Clone
        </h1>
        <p style={{ fontSize: '1.1rem', color: 'var(--c-text-muted)', maxWidth: 600, margin: '0 auto 1.5rem' }}>
          AI 人物风格档案 / AI 记忆对话库 — 上传资料，生成画像，对话回溯
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

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '1rem' }}>
        <FeatureCard
          title="人物档案管理"
          desc="创建和管理多个人物档案，记录基本信息和关系类型。"
          icon="📋"
        />
        <FeatureCard
          title="智能资料解析"
          desc="支持 txt、md、json、csv 等多种格式，自动清洗、切分、去重并建立向量索引。"
          icon="📄"
        />
        <FeatureCard
          title="AI 人物画像"
          desc="基于上传资料自动生成详细的人物画像报告和风格卡，包括常用表达、情绪倾向、价值观等。"
          icon="🎯"
        />
        <FeatureCard
          title="RAG 记忆对话"
          desc="基于资料检索增强的对话机器人，以模拟角色方式回答，严格遵循合规边界。"
          icon="💬"
        />
        <FeatureCard
          title="多 Provider 支持"
          desc="支持 OpenAI、DeepSeek、OpenRouter、Qwen 等兼容 API，也可在 Mock 模式下无 API Key 体验。"
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
