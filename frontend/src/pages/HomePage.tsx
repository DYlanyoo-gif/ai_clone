import { useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'

type ScenarioKey = 'customer' | 'relationship' | 'creator' | 'candidate' | 'personal'
type OutputKey = 'portrait' | 'evidence' | 'runtime' | 'advice' | 'report'

const scenarioItems: Array<{
  key: ScenarioKey
  title: string
  subtitle: string
  upload: string[]
  analyze: string[]
  result: string[]
}> = [
  {
    key: 'customer',
    title: '客户沟通分析',
    subtitle: '把销售、客服、商务沟通整理成可追溯的客户理解。',
    upload: ['客户聊天记录', '销售沟通文本', '客服对话', '邮件往来'],
    analyze: ['关注点', '表达风格', '决策倾向', '风险信号', '沟通边界'],
    result: ['证据化画像', '沟通建议', '关键证据', '模拟问答', 'Markdown 报告'],
  },
  {
    key: 'relationship',
    title: '朋友 / 伴侣沟通理解',
    subtitle: '基于授权聊天资料，理解沟通习惯、情绪触发点和边界。',
    upload: ['已授权聊天文本', '长期沟通记录', '关系事件记录', '语音整理文本'],
    analyze: ['情绪模式', '关系边界', '冲突触发点', '表达习惯', '资料缺口'],
    result: ['沟通画像', '边界提醒', '风险提示', '对话建议', '证据摘录'],
  },
  {
    key: 'creator',
    title: '博主 / IP 风格拆解',
    subtitle: '从公开内容里提取语言风格、内容逻辑和表达 DNA。',
    upload: ['公众号文章', '小红书内容', '推文合集', '博客项目复盘'],
    analyze: ['语言节奏', '内容结构', '常用表达', '价值观线索', '互动风格'],
    result: ['风格画像', '表达模板', '内容逻辑', '模拟示例', '完整报告'],
  },
  {
    key: 'candidate',
    title: '候选人 / 合作者资料整理',
    subtitle: '把简历、访谈和公开资料转成证据化理解框架。',
    upload: ['简历摘要', '访谈稿', '会议纪要', '公开资料'],
    analyze: ['决策习惯', '协作方式', '关注重点', '风险点', '沟通节奏'],
    result: ['人物摘要', '协作建议', '证据链', '资料不足项', '报告导出'],
  },
  {
    key: 'personal',
    title: '个人数字档案',
    subtitle: '整理自己的文章、聊天记录和笔记，建立个人表达画像。',
    upload: ['个人文章', '聊天记录', '读书笔记', '工作复盘'],
    analyze: ['表达风格', '思维模式', '情绪模式', '决策路径', '长期变化'],
    result: ['个人画像', '风格卡', '模拟实验台', '资料地图', '导出报告'],
  },
]

const outputPreviews: Array<{
  key: OutputKey
  label: string
  eyebrow: string
  title: string
  bullets: string[]
  meta: string[]
}> = [
  {
    key: 'portrait',
    label: '人物画像',
    eyebrow: 'Profile Module',
    title: '语言风格与决策习惯',
    bullets: ['语言风格：理性、自省，转折较多', '决策习惯：先观察，再拆解问题', '资料不足：缺少即时聊天记录'],
    meta: ['14 模块', '证据覆盖率', '置信度'],
  },
  {
    key: 'evidence',
    label: '证据链',
    eyebrow: 'Evidence Map',
    title: '每个判断都能回到资料来源',
    bullets: ['chunk #18 · 项目复盘.txt', 'source: 沟通记录 / 会议纪要', 'confidence: 86 / 100'],
    meta: ['quote', 'source', 'confidence'],
  },
  {
    key: 'runtime',
    label: '模拟实验台',
    eyebrow: 'Runtime Lab',
    title: '站内运行双引擎模拟',
    bullets: ['用户：复杂选择时会怎么判断？', '回答：会先压低情绪噪声，再找最小行动。', '系统：同时标注证据与不确定性。'],
    meta: ['画像引擎', '交互引擎', '对比模拟'],
  },
  {
    key: 'advice',
    label: '沟通建议',
    eyebrow: 'Communication Guide',
    title: '更稳妥的下一句怎么说',
    bullets: ['先确认对方关注点', '避免强行替对方下结论', '对资料不足部分明确保留'],
    meta: ['边界', '风险', '建议'],
  },
  {
    key: 'report',
    label: '报告导出',
    eyebrow: 'Export',
    title: '从分析到交付的完整材料',
    bullets: ['Markdown 分析报告', '结构化风格卡', 'RAG / SFT 数据集'],
    meta: ['Report', 'Dataset', '风格卡'],
  },
]

const flowSteps = [
  ['上传资料', '导入你有权使用的文本、聊天记录或复杂文档。'],
  ['一键分析', '系统解析资料并生成可引用的文本片段。'],
  ['证据画像', '生成 14 模块人物画像、证据链和置信度。'],
  ['站内模拟', '运行思维模拟、互动模拟和对比分析。'],
  ['导出报告', '交付 Markdown 报告和结构化资料。'],
]

export default function HomePage() {
  const [activeScenario, setActiveScenario] = useState<ScenarioKey>('customer')
  const [activeOutput, setActiveOutput] = useState<OutputKey>('portrait')

  const scenario = scenarioItems.find(item => item.key === activeScenario) || scenarioItems[0]
  const output = outputPreviews.find(item => item.key === activeOutput) || outputPreviews[0]

  const handleScenarioKey = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    const currentIndex = scenarioItems.findIndex(item => item.key === activeScenario)
    const nextIndex = event.key === 'ArrowRight'
      ? (currentIndex + 1) % scenarioItems.length
      : (currentIndex - 1 + scenarioItems.length) % scenarioItems.length
    setActiveScenario(scenarioItems[nextIndex].key)
  }

  return (
    <div className="home-page product-home fade-in">
      <section className="home-hero-redesign">
        <div className="home-hero-copy">
          <div className="hero-kicker">Evidence Profile Workbench</div>
          <h1>证据化人物画像</h1>
          <p>
            上传聊天记录、文章、客户沟通记录或复杂文档，系统会生成带证据链的人物画像，并在网页内运行引擎模拟。
          </p>
          <div className="hero-actions">
            <Link to="/profiles" className="btn-primary">开始创建人物档案</Link>
            <Link to="/profiles" className="btn-secondary">查看人物档案</Link>
          </div>
        </div>
        <div className="portrait-visual glass-panel" aria-label="动态人物画像预览">
          <svg className="portrait-lines" viewBox="0 0 420 420" aria-hidden="true">
            <path className="portrait-line line-a" d="M88 126 C152 78 246 74 316 128" />
            <path className="portrait-line line-b" d="M78 282 C144 335 260 342 338 260" />
            <path className="portrait-line line-c" d="M112 204 C174 168 250 176 306 218" />
          </svg>
          <div className="portrait-orbit orbit-one">
            <span className="portrait-node node-a" />
            <span className="portrait-node node-b" />
          </div>
          <div className="portrait-orbit orbit-two">
            <span className="portrait-node node-c" />
            <span className="portrait-node node-d" />
          </div>
          <div className="portrait-face">
            <span className="face-axis vertical" />
            <span className="face-axis horizontal" />
            <span className="face-point p1" />
            <span className="face-point p2" />
            <span className="face-point p3" />
            <span className="face-point p4" />
          </div>
          <div className="portrait-evidence-card card-a">
            <span>证据片段</span>
            <strong>“先观察，再拆解”</strong>
          </div>
          <div className="portrait-evidence-card card-b">
            <span>画像结论</span>
            <strong>理性、自省、边界清晰</strong>
          </div>
          <div className="portrait-evidence-card card-c">
            <span>模拟状态</span>
            <strong><i className="signal-dot active" /> 已准备</strong>
          </div>
        </div>
      </section>

      <div className="home-belief-strip glass-panel">
        <span className="signal-dot" />
        <p>我们坚信人是习惯动物，任何发生的事情与行为都是有迹可循的、有规律的。</p>
      </div>

      <section className="scenario-console glass-panel" onKeyDown={handleScenarioKey} tabIndex={0}>
        <div className="section-title" style={{ marginTop: 0 }}>
          <div>
            <span className="section-eyebrow">Scenario Console</span>
            <h2>场景画像工作台</h2>
            <p>先选择你要理解的关系或资料场景，再决定该上传什么、分析什么、交付什么。</p>
          </div>
        </div>
        <div className="scenario-studio-grid">
          <div className="scenario-selector" role="tablist" aria-label="场景选择">
            {scenarioItems.map(item => (
              <button
                key={item.key}
                type="button"
                role="tab"
                aria-selected={activeScenario === item.key}
                className={activeScenario === item.key ? 'active' : ''}
                onClick={() => setActiveScenario(item.key)}
              >
                <strong>{item.title}</strong>
                <span>{item.subtitle}</span>
              </button>
            ))}
          </div>
          <div className="scenario-detail-panel slide-up" key={scenario.key}>
            <span className="badge badge-info">{scenario.title}</span>
            <h3>{scenario.subtitle}</h3>
            <div className="scenario-detail-grid">
              <ScenarioColumn title="适合上传" items={scenario.upload} />
              <ScenarioColumn title="系统会分析" items={scenario.analyze} />
              <ScenarioColumn title="你会得到" items={scenario.result} />
            </div>
            <div className="scenario-next-step">
              <div>
                <strong>下一步</strong>
                <p>创建人物档案，上传已授权资料后即可开始分析。</p>
              </div>
              <Link to="/profiles" className="btn-primary">创建档案并上传资料</Link>
            </div>
          </div>
        </div>
      </section>

      <section className="output-preview glass-panel">
        <div className="section-title" style={{ marginTop: 0 }}>
          <div>
            <h2>Output Preview</h2>
            <p>结果以报告、证据、模拟和建议组织，而不是一堆技术状态。</p>
          </div>
        </div>
        <div className="output-preview-grid">
          <div className="output-tabs" role="tablist" aria-label="输出类型">
            {outputPreviews.map(item => (
              <button
                key={item.key}
                type="button"
                className={activeOutput === item.key ? 'active' : ''}
                onClick={() => setActiveOutput(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <article className="mock-report-card slide-up" key={output.key}>
            <div className="mock-report-head">
              <span>{output.eyebrow}</span>
              <strong>{output.title}</strong>
            </div>
            <div className="mock-report-lines">
              {output.bullets.map(item => <p key={item}>{item}</p>)}
            </div>
            <div className="mock-report-tags">
              {output.meta.map(item => <span key={item}>{item}</span>)}
            </div>
          </article>
        </div>
      </section>

      <section className="compact-how-it-works">
        {flowSteps.map(([title, desc], index) => (
          <div className="compact-flow-step" key={title}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <strong>{title}</strong>
            <p>{desc}</p>
          </div>
        ))}
      </section>
    </div>
  )
}

function ScenarioColumn({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="scenario-column">
      <strong>{title}</strong>
      <ul>
        {items.map(item => <li key={item}>{item}</li>)}
      </ul>
    </div>
  )
}
