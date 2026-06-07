import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  getMineruStatus, getConfigStatus, getVectorStatus,
  getNuwaStatus, getColleagueStatus,
  type MineruStatus, type ConfigStatus,
  type VectorStatus, type SkillIntegrationStatus,
} from '../api/client'

type StackTone = 'success' | 'info' | 'muted' | 'warning'

interface StackItem {
  name: string
  statusText: string
  tone: StackTone
  desc: string
}

const importMaterials = [
  {
    title: '聊天记录导出文本',
    desc: '微信 / QQ / Telegram 等已授权整理的聊天记录文本。',
  },
  {
    title: '客户沟通记录',
    desc: '销售对话、客服记录、客户访谈和长期沟通纪要。',
  },
  {
    title: '关系沟通资料',
    desc: '朋友、伴侣、同事之间已获得授权的沟通资料。',
  },
  {
    title: '公开内容',
    desc: '博客、公众号、朋友圈、小红书、推文等公开或已授权内容。',
  },
  {
    title: '职业资料',
    desc: '简历、访谈稿、会议纪要、邮件和项目沟通记录。',
  },
  {
    title: '复杂文档',
    desc: 'PDF / Word / 图片等需要解析整理的多格式资料。',
  },
]

const resultItems = [
  '人物画像与性格倾向',
  '语言风格和常用表达',
  '沟通方式与关系边界',
  '决策习惯与情绪模式',
  '冲突风险和资料不足提示',
  '证据链和置信度',
  'Nuwa / Colleague 双引擎模拟实验台',
  '完整 Markdown 分析报告导出',
]

const scenarios = [
  {
    title: '客户沟通分析',
    desc: '分析客户关注点、表达风格、决策倾向，辅助后续沟通。',
  },
  {
    title: '朋友 / 伴侣沟通理解',
    desc: '基于已授权聊天资料，理解对方沟通习惯、情绪触发点和边界。',
  },
  {
    title: '博主 / IP 风格拆解',
    desc: '分析公开文章、推文、公众号内容，提取语言风格和内容逻辑。',
  },
  {
    title: '候选人 / 合作者资料整理',
    desc: '基于简历、访谈、公开资料生成证据化画像，辅助理解沟通方式。',
  },
  {
    title: '个人数字档案',
    desc: '整理自己的文章、聊天记录、笔记，生成个人表达风格和思维画像。',
  },
]

const flowSteps = [
  ['01', '导入授权资料', '上传聊天记录文本、公开内容、简历、PDF、Word 或图片等资料。'],
  ['02', '整理为可分析文本', '系统解析复杂文档，并把资料整理为可追溯的文本片段。'],
  ['03', '生成证据化画像', '输出人物画像、表达风格、关系边界、风险提示和置信度。'],
  ['04', '进入模拟实验台', '运行 Nuwa 思维模拟、Colleague 互动模拟或双引擎对比。'],
  ['05', '导出报告', '生成 Markdown 分析报告，也可导出 RAG / SFT 数据集。'],
]

function badgeClass(tone: StackTone): string {
  const map: Record<StackTone, string> = {
    success: 'badge badge-success',
    info: 'badge badge-info',
    muted: 'badge badge-muted',
    warning: 'badge badge-warning',
  }
  return map[tone]
}

export default function HomePage() {
  const [mineru, setMineru] = useState<MineruStatus | null>(null)
  const [config, setConfig] = useState<ConfigStatus | null>(null)
  const [vector, setVector] = useState<VectorStatus | null>(null)
  const [nuwa, setNuwa] = useState<SkillIntegrationStatus | null>(null)
  const [colleague, setColleague] = useState<SkillIntegrationStatus | null>(null)

  useEffect(() => {
    getMineruStatus().then(setMineru).catch(() => {})
    getConfigStatus().then(setConfig).catch(() => {})
    getVectorStatus().then(setVector).catch(() => {})
    getNuwaStatus().then(setNuwa).catch(() => {})
    getColleagueStatus().then(setColleague).catch(() => {})
  }, [])

  const stackItems: StackItem[] = [
    {
      name: 'DeepSeek',
      statusText: config && !config.is_mock ? '已接入' : '服务配置中',
      tone: config && !config.is_mock ? 'success' : 'muted',
      desc: '画像与模拟生成引擎，用于生成证据化分析、风格总结和模拟回答。',
    },
    {
      name: 'MinerU',
      statusText: mineru?.enabled ? '已启用' : '可协助处理',
      tone: mineru?.enabled ? 'success' : 'info',
      desc: '复杂文档解析能力，支持 PDF、Office、图片等资料整理。',
    },
    {
      name: 'Persona Skill Foundry',
      statusText: nuwa?.available || colleague?.available ? '已接入' : '服务配置中',
      tone: nuwa?.available || colleague?.available ? 'success' : 'muted',
      desc: 'Nuwa / Colleague 双引擎，用于站内人物模拟实验台。',
    },
    {
      name: '基础检索',
      statusText: '已启用',
      tone: 'success',
      desc: '默认证据检索能力，保障画像、证据弹窗和模拟问答可用。',
    },
    {
      name: '语义检索增强',
      statusText: vector?.available ? '已启用' : '管理员可选',
      tone: vector?.available ? 'success' : 'info',
      desc: '资料量较大时可启用语义检索，提升证据命中质量。',
    },
    {
      name: '数据导出',
      statusText: '已支持',
      tone: 'success',
      desc: '支持完整分析报告、RAG Dataset 和 SFT Dataset 导出。',
    },
  ]

  return (
    <div className="home-page fade-in">
      <section className="card hero-panel service-hero">
        <div>
          <div className="hero-kicker">Evidence Profile Service</div>
          <h1>把授权资料整理成可追溯的人物画像和模拟实验台</h1>
          <p>
            你提供有权使用的聊天记录、公开内容或文档资料，系统会整理证据、生成画像结论，
            并给出可查看来源的模拟回答和 Markdown 报告。
          </p>
          <p className="hero-note">
            生成结果是基于资料的分析与模拟，不是本人意识，也不代表本人真实意愿。
          </p>
          <div className="hero-actions">
            <Link to="/profiles" className="btn-primary">进入人物档案</Link>
            <a href="#contact" className="btn-secondary">联系资料整理服务</a>
          </div>
        </div>
        <div className="hero-side service-hero-side">
          <div className="metric-card">
            <div className="metric-label">Materials</div>
            <div className="metric-value">聊天 / 文档 / 公开内容</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Outputs</div>
            <div className="metric-value">画像 · 证据 · 报告</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Runtime</div>
            <div className="metric-value">Nuwa / Colleague</div>
          </div>
        </div>
      </section>

      <section id="materials">
        <div className="section-title">
          <div>
            <h2>适合导入的资料</h2>
            <p>系统适合处理已经整理好、可授权使用、需要进一步分析的人物资料。</p>
          </div>
        </div>
        <div className="service-grid">
          {importMaterials.map((item, index) => (
            <ServiceCard key={item.title} index={String(index + 1).padStart(2, '0')} title={item.title} desc={item.desc} />
          ))}
        </div>
        <div className="compliance-panel">
          <strong>合规边界</strong>
          <p>
            只支持用户有权使用或已获得授权的资料。不提供未授权聊天记录获取、破解、绕过登录、
            恢复他人隐私数据等服务，也不得用于冒充真人、诈骗、骚扰或操控关系。
          </p>
        </div>
      </section>

      <section id="results">
        <div className="section-title">
          <div>
            <h2>能得到什么结果</h2>
            <p>输出不是空泛总结，而是带证据、置信度和资料不足提示的分析结果。</p>
          </div>
        </div>
        <div className="result-grid">
          {resultItems.map(item => (
            <div className="result-item" key={item}>
              <span />
              <strong>{item}</strong>
            </div>
          ))}
        </div>
      </section>

      <section id="scenarios">
        <div className="section-title">
          <div>
            <h2>使用场景</h2>
            <p>更适合做理解、整理和辅助沟通，不用于代替本人表达真实意愿。</p>
          </div>
        </div>
        <div className="scenario-grid">
          {scenarios.map((item, index) => (
            <article className="card scenario-card hover-lift" key={item.title}>
              <span className="feature-index">{String(index + 1).padStart(2, '0')}</span>
              <h3>{item.title}</h3>
              <p>{item.desc}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="flow">
        <div className="section-title">
          <div>
            <h2>服务流程</h2>
            <p>从资料导入到报告导出，普通用户不需要理解内部工程状态。</p>
          </div>
        </div>
        <div className="flow-strip service-flow">
          {flowSteps.map(([idx, title, desc]) => (
            <div className="flow-step slide-up" key={idx}>
              <span>{idx}</span>
              <strong>{title}</strong>
              <p>{desc}</p>
            </div>
          ))}
        </div>
      </section>

      <section id="contact" className="card contact-panel">
        <div>
          <span className="badge badge-info">联系服务</span>
          <h2>需要协助整理资料或复杂文档？</h2>
          <p>
            如果你需要协助整理微信 / QQ 聊天记录、客户沟通记录、复杂 PDF / Word 文档，
            可以联系我进行资料整理与分析服务。
          </p>
        </div>
        <div className="contact-box">
          <strong>微信 / QQ / 邮箱</strong>
          <p>请在这里填写</p>
        </div>
      </section>

      <section className="technical-note-section">
        <div className="section-title">
          <div>
            <h2>技术能力说明</h2>
            <p>以下为后台能力概览；安装、依赖和管理员诊断信息不在普通首页展示。</p>
          </div>
        </div>
        <div className="stack-grid compact-stack-grid">
          {stackItems.map(item => (
            <article className="card stack-card compact-stack-card hover-lift" key={item.name}>
              <header>
                <div>
                  <h3>{item.name}</h3>
                  <p>{item.desc}</p>
                </div>
                <span className={badgeClass(item.tone)}>{item.statusText}</span>
              </header>
            </article>
          ))}
        </div>
      </section>
    </div>
  )
}

function ServiceCard({ index, title, desc }: { index: string; title: string; desc: string }) {
  return (
    <article className="card service-card hover-lift">
      <span className="feature-index">{index}</span>
      <h3>{title}</h3>
      <p>{desc}</p>
    </article>
  )
}
