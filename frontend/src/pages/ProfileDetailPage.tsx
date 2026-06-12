import { useState, useEffect, useRef, useCallback, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import {
  getProfile, uploadDocument, uploadTextAsDocument, listDocuments,
  runProfilePipeline, type Profile, type Document,
  getConfigStatus, exportSkillCard, exportDataset,
  getSufficiency, type DataSufficiency, type ConfigStatus,
  getMineruStatus, type MineruStatus,
  deleteDocument, previewDocument, rebuildChunks,
  exportSFT, type DocumentPreview,
  exportAnalysisReport, type EvidenceMap, type EvidenceModule, type EvidenceClaim,
  getVectorStatus, rebuildVectorIndex, type VectorStatus,
  getMem0Status, type Mem0Status,
  getNuwaStatus, getColleagueStatus, getNuwaSpec, getColleagueSpec,
  generateNuwaSkill, generateColleagueSkill, listGeneratedSkills,
  generatedSkillDownloadUrl, type SkillIntegrationStatus, type SkillSpec,
  validateGeneratedSkill, dryRunGeneratedSkill, getSkillInstallInstructions,
  generateRuntimeTestCases, getRuntimeTestCases, submitRuntimeResult, evaluateRuntimeResult,
  runWebsiteSkill, listWebsiteSkillRuns, compareWebsiteSkills, submitWebsiteSkillRunFeedback,
  isNotFoundError,
  type GeneratedSkill, type SkillValidationResult, type RuntimeTestCasesResult,
  type RuntimeEvaluationResult, type RuntimeResultSubmission,
  type SkillRuntimeMode, type SkillWebsiteRun, type SkillCompareRunResult,
  type SkillRuntimeFeedbackPayload, type ProfilePipelineResult, type PipelineStepStatusName,
} from '../api/client'

// Parse Markdown into sections by H2 headers
function parseMarkdownSections(md: string): { title: string; content: string; anchor: string }[] {
  if (!md) return []
  // Remove the top-level H1 and compliance blockquote
  const body = md.replace(/^# .*\n/, '').replace(/^> .*\n/gm, '').trim()
  // Split on "## N. " pattern
  const sections = body.split(/\n(?=## \d+\. )/)
  return sections.map(s => {
    const match = s.match(/^## (\d+\. .+)/)
    const title = match ? match[1] : s.split('\n')[0].replace(/^## /, '')
    const anchor = title.replace(/[^\w一-鿿]/g, '-').replace(/-+/g, '-').toLowerCase()
    return { title, content: s.trim(), anchor }
  }).filter(s => s.title)
}

// Parse style card sections similarly
function parseStyleCardSections(md: string): { title: string; content: string; anchor: string }[] {
  if (!md) return []
  const sections = md.split(/\n(?=## \d+\. )/)
  return sections.map(s => {
    const title = s.split('\n')[0].replace(/^## /, '')
    const anchor = title.replace(/[^\w一-鿿]/g, '-').replace(/-+/g, '-').toLowerCase()
    return { title, content: s.trim(), anchor }
  }).filter(s => s.title)
}

function relationshipLabel(t: string): string {
  const map: Record<string, string> = {
    friend: '朋友', family: '亲人', colleague: '同事',
    lover: '伴侣/白月光', public_figure: '公众人物',
    author: '作者/IP', celebrity: '知名人物', other: '其他',
  }
  return map[t] || t
}

const RUNTIME_EXAMPLE_PROMPTS = [
  '这个人遇到复杂选择时会怎么判断？',
  '请基于证据分析这个人的沟通风格。',
  '资料不足时你会如何回答？',
  '两个模拟视角对同一问题有什么不同？',
]

const PAGE_NAV_ITEMS = [
  { id: 'overview', label: '总览' },
  { id: 'runtime', label: '模拟实验台' },
  { id: 'portrait', label: '画像' },
  { id: 'documents', label: '资料' },
  { id: 'exports', label: '导出' },
  { id: 'advanced', label: '高级' },
]

type WorkbenchTab = 'overview' | 'runtime' | 'portrait' | 'documents' | 'exports'
type PortraitFilter = 'all' | 'evidence' | 'insufficient' | 'high' | 'low'
type DocumentInputMode = 'upload' | 'paste'
type PasteMeterLevel = 'empty' | 'poor' | 'starter' | 'solid' | 'rich'

const PASTE_CHUNK_SIZE = 800

function getDefaultDocumentInputMode(): DocumentInputMode {
  if (typeof window === 'undefined') return 'upload'
  if (!window.matchMedia) return 'upload'
  return window.matchMedia('(max-width: 640px)').matches ? 'paste' : 'upload'
}

function countTextCharacters(text: string): number {
  return Array.from(text.trim()).length
}

function getPasteMeter(charCount: number): { level: PasteMeterLevel; label: string; hint: string; percent: number } {
  if (charCount <= 0) {
    return { level: 'empty', label: '等待输入', hint: '直接粘贴聊天记录、文章、客户沟通内容或其他文本资料。', percent: 0 }
  }
  if (charCount < 100) {
    return { level: 'poor', label: '不足', hint: '资料较少，画像可能不稳定', percent: Math.max(8, Math.round(charCount)) }
  }
  if (charCount < 1000) {
    return { level: 'starter', label: '可分析', hint: '资料可用于初步分析', percent: 34 + Math.round((charCount - 100) / 900 * 20) }
  }
  if (charCount < 5000) {
    return { level: 'solid', label: '较充分', hint: '资料较充分，可生成更稳定的画像', percent: 58 + Math.round((charCount - 1000) / 4000 * 26) }
  }
  return { level: 'rich', label: '充分', hint: '内容较长，保存后将自动分片', percent: 100 }
}

function sanitizeDocumentTitle(title: string): string {
  return title
    .trim()
    .replace(/[\\/:*?"<>|#%{}\[\]~`^]/g, '-')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 80)
}

function buildPastedFilename(profileId: number, title: string): string {
  const cleanTitle = sanitizeDocumentTitle(title)
  if (cleanTitle) return `${cleanTitle}.txt`
  return `pasted-profile-${profileId}-${Date.now()}.txt`
}

const WORKBENCH_TABS: { id: WorkbenchTab; label: string; hint: string }[] = [
  { id: 'overview', label: '总览', hint: '状态与下一步' },
  { id: 'runtime', label: '模拟', hint: '思维 / 互动 / 对比' },
  { id: 'portrait', label: '画像', hint: '14 模块证据画像' },
  { id: 'documents', label: '资料', hint: '上传与文件管理' },
  { id: 'exports', label: '导出', hint: '报告与高级导出' },
]

const HASH_TO_TAB: Record<string, WorkbenchTab> = {
  overview: 'overview',
  profile: 'portrait',
  portrait: 'portrait',
  runtime: 'runtime',
  files: 'documents',
  documents: 'documents',
  exports: 'exports',
}

const TAB_TO_HASH: Record<WorkbenchTab, string> = {
  overview: 'overview',
  runtime: 'runtime',
  portrait: 'profile',
  documents: 'files',
  exports: 'exports',
}

function getInitialWorkbenchTab(): WorkbenchTab {
  if (typeof window === 'undefined') return 'overview'
  const key = window.location.hash.replace(/^#/, '')
  return HASH_TO_TAB[key] || 'overview'
}

type PipelineStepKey = 'parse' | 'analysis' | 'nuwa' | 'colleague' | 'runtime'
type PipelineUiStatus = PipelineStepStatusName | 'pending'

const PIPELINE_STEPS: { key: PipelineStepKey; title: string; desc: string }[] = [
  { key: 'parse', title: '解析资料', desc: '读取已上传文档和文本片段' },
  { key: 'analysis', title: '生成证据画像', desc: '生成 14 模块画像和证据链' },
  { key: 'nuwa', title: '准备思维模拟', desc: '整理思维模拟能力' },
  { key: 'colleague', title: '准备互动模拟', desc: '整理互动模拟能力' },
  { key: 'runtime', title: '准备模拟实验台', desc: '开放站内运行入口' },
]

const createPipelineSteps = (status: PipelineUiStatus = 'pending') =>
  PIPELINE_STEPS.reduce((acc, item) => {
    acc[item.key] = status
    return acc
  }, {} as Record<PipelineStepKey, PipelineUiStatus>)

function toPipelineUiStatus(status?: string | null): PipelineUiStatus {
  if (status === 'running' || status === 'done' || status === 'warning' || status === 'failed') return status
  return 'pending'
}

function isRunnableSkill(skill?: GeneratedSkill): skill is GeneratedSkill {
  return Boolean(skill?.compatible_skill_generated && skill.output_path)
}

const RUNTIME_MODE_OPTIONS: { value: SkillRuntimeMode; label: string; hint: string }[] = [
  { value: 'nuwa_thinking', label: '思维模拟', hint: '心智模型与决策启发式' },
  { value: 'colleague_interaction', label: '互动模拟', hint: '互动规则与协作方式' },
  { value: 'evidence_check', label: '证据检查', hint: '证据引用与事实约束' },
  { value: 'uncertainty_check', label: '不确定性检查', hint: '资料不足时的边界表达' },
  { value: 'compare', label: '对比模拟', hint: '双引擎差异对比' },
]

function runtimeModeLabel(mode: SkillRuntimeMode | string): string {
  return RUNTIME_MODE_OPTIONS.find(item => item.value === mode)?.label || mode
}

function skillTypeLabel(type: 'nuwa' | 'colleague' | 'compare'): string {
  if (type === 'compare') return '对比模拟'
  return type === 'nuwa' ? '思维模拟' : '互动模拟'
}

function defaultSourceRepo(type: 'nuwa' | 'colleague'): string {
  return type === 'nuwa' ? 'external/nuwa-skill' : 'external/colleague-skill'
}

function compareDimensionLabel(dimension: string): string {
  const normalized = dimension.toLowerCase().replace(/[_-]/g, ' ')
  const map: Record<string, string> = {
    'thinking framework': '思维框架',
    'thinking style': '思维框架',
    'interaction rules': '互动规则',
    'relationship workflow': '互动规则',
    'evidence citation': '证据引用',
    'evidence usage': '证据引用',
    uncertainty: '不确定性',
    'uncertainty handling': '不确定性',
    'suitable scenarios': '适合场景',
    'best fit': '适合场景',
  }
  return map[normalized] || dimension
}

function summarizeMarkdown(md: string, fallback = '暂无摘要。'): string {
  const cleaned = md
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`~\-[\]()]/g, ' ')
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .find(line => line.length > 12)
  if (!cleaned) return fallback
  return cleaned.length > 96 ? `${cleaned.slice(0, 96)}...` : cleaned
}

function summarizeEvidenceModule(evidence: EvidenceModule | null, fallbackContent: string): string {
  const firstClaim = evidence?.claims?.find(claim => claim.claim)?.claim
  return firstClaim || summarizeMarkdown(fallbackContent)
}

export default function ProfileDetailPage() {
  const { id } = useParams<{ id: string }>()
  const profileId = Number(id)
  const isValidId = id && Number.isFinite(profileId) && profileId > 0

  const [profile, setProfile] = useState<Profile | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [configStatus, setConfigStatus] = useState<ConfigStatus | null>(null)
  const [mineruStatus, setMineruStatus] = useState<MineruStatus | null>(null)
  const [vectorStatus, setVectorStatus] = useState<VectorStatus | null>(null)
  const [mem0Status, setMem0Status] = useState<Mem0Status | null>(null)
  const [nuwaStatus, setNuwaStatus] = useState<SkillIntegrationStatus | null>(null)
  const [colleagueStatus, setColleagueStatus] = useState<SkillIntegrationStatus | null>(null)
  const [generatedSkills, setGeneratedSkills] = useState<GeneratedSkill[]>([])
  const [skillSpec, setSkillSpec] = useState<SkillSpec | null>(null)
  const [sufficiency, setSufficiency] = useState<DataSufficiency | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [documentInputMode, setDocumentInputMode] = useState<DocumentInputMode>(() => getDefaultDocumentInputMode())
  const [pasteTitle, setPasteTitle] = useState('')
  const [pasteText, setPasteText] = useState('')
  const [pasteSaving, setPasteSaving] = useState(false)
  const [pasteNotice, setPasteNotice] = useState('')
  const [pasteHighlighted, setPasteHighlighted] = useState(false)
  const [exporting, setExporting] = useState('')
  const [copied, setCopied] = useState('')
  const [pipelineResult, setPipelineResult] = useState<ProfilePipelineResult | null>(null)
  const [pipelineSteps, setPipelineSteps] = useState<Record<PipelineStepKey, PipelineUiStatus>>(createPipelineSteps())
  const [activeSection, setActiveSection] = useState('')
  const [uploadingFileName, setUploadingFileName] = useState('')
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [previewDoc, setPreviewDoc] = useState<DocumentPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [rebuilding, setRebuilding] = useState(false)
  const [vectorRebuilding, setVectorRebuilding] = useState(false)
  const [generatingSkill, setGeneratingSkill] = useState('')
  const [validatingSkill, setValidatingSkill] = useState<number | null>(null)
  const [dryRunningSkill, setDryRunningSkill] = useState<number | null>(null)
  const [installingSkill, setInstallingSkill] = useState<number | null>(null)
  const [dryRunResult, setDryRunResult] = useState<SkillValidationResult | null>(null)
  const [runtimeBusySkill, setRuntimeBusySkill] = useState<number | null>(null)
  const [runtimeCases, setRuntimeCases] = useState<RuntimeTestCasesResult | null>(null)
  const [runtimeModalSkill, setRuntimeModalSkill] = useState<GeneratedSkill | null>(null)
  const [runtimeForm, setRuntimeForm] = useState<RuntimeResultSubmission>({
    runtime_target: 'codex',
    tester_note: '',
    test_output_text: '',
    evidence_of_runtime: '',
  })
  const [runtimeEvaluation, setRuntimeEvaluation] = useState<RuntimeEvaluationResult | null>(null)
  const [websiteRuns, setWebsiteRuns] = useState<Record<number, SkillWebsiteRun[]>>({})
  const [runtimeLabSkillType, setRuntimeLabSkillType] = useState<'nuwa' | 'colleague' | 'compare'>('nuwa')
  const [runtimeLabMode, setRuntimeLabMode] = useState<SkillRuntimeMode>('evidence_check')
  const [runtimePrompt, setRuntimePrompt] = useState('')
  const [websiteRuntimeRunning, setWebsiteRuntimeRunning] = useState(false)
  const [websiteRuntimeResult, setWebsiteRuntimeResult] = useState<SkillWebsiteRun | null>(null)
  const [compareRuntimeResult, setCompareRuntimeResult] = useState<SkillCompareRunResult | null>(null)
  const [runtimeTraceOpen, setRuntimeTraceOpen] = useState(false)
  const [feedbackRating, setFeedbackRating] = useState<SkillRuntimeFeedbackPayload['rating']>('good')
  const [feedbackNote, setFeedbackNote] = useState('')
  const [feedbackExpanded, setFeedbackExpanded] = useState(false)
  const [feedbackBusy, setFeedbackBusy] = useState(false)
  const [evidenceModal, setEvidenceModal] = useState<{ moduleName: string; moduleIndex: string } | null>(null)
  const [advancedOpen, setAdvancedOpen] = useState(() => localStorage.getItem('profile-detail-advanced-open-v3') === 'true')
  const [expandedPortraitModules, setExpandedPortraitModules] = useState<Record<string, boolean>>({})
  const adminView = false
  const [activeWorkbenchTab, setActiveWorkbenchTab] = useState<WorkbenchTab>(() => getInitialWorkbenchTab())
  const [portraitFilter, setPortraitFilter] = useState<PortraitFilter>('all')
  const [portraitDrawer, setPortraitDrawer] = useState<{ title: string; content: string; moduleNo: string; evidence: EvidenceModule | null } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pasteTextRef = useRef<HTMLTextAreaElement>(null)
  const pasteHighlightTimerRef = useRef<number | null>(null)
  const runtimePromptRef = useRef<HTMLTextAreaElement>(null)
  const pipelineTimerRef = useRef<number | null>(null)

  // Parse evidence map from latest analysis
  const evidenceMap: EvidenceMap = (() => {
    if (!profile?.evidence_json) return {}
    try {
      return JSON.parse(profile.evidence_json)
    } catch {
      return {}
    }
  })()
  const latestNuwaSkill = generatedSkills.find(s => s.skill_type === 'nuwa')
  const latestColleagueSkill = generatedSkills.find(s => s.skill_type === 'colleague')
  const pastedCharCount = countTextCharacters(pasteText)
  const pastedChunkEstimate = pastedCharCount > 0 ? Math.max(1, Math.ceil(pastedCharCount / PASTE_CHUNK_SIZE)) : 0
  const pasteMeter = getPasteMeter(pastedCharCount)
  const canSavePastedText = pastedCharCount > 0 && !pasteSaving && !uploading

  const refreshWebsiteRuns = useCallback(async () => {
    if (!isValidId) return
    const targets = [latestNuwaSkill, latestColleagueSkill].filter(Boolean) as GeneratedSkill[]
    if (targets.length === 0) return
    const entries = await Promise.all(
      targets.map(async skill => {
        const runs = await listWebsiteSkillRuns(profileId, skill.id).catch((e: any) => {
          if (!isNotFoundError(e)) console.warn('Website runtime runs unavailable', e)
          return []
        })
        return [skill.id, runs] as const
      })
    )
    setWebsiteRuns(prev => ({ ...prev, ...Object.fromEntries(entries) }))
  }, [isValidId, profileId, latestNuwaSkill?.id, latestColleagueSkill?.id])

  const fetchData = useCallback(async () => {
    if (!isValidId) return
    try {
      setLoading(true)
      setError('')
      const [p, docs, cfg, mineru, vector, mem0, suff, nuwa, colleague, skills] = await Promise.all([
        getProfile(profileId),
        listDocuments(profileId),
        getConfigStatus().catch(() => null),
        getMineruStatus().catch(() => null),
        getVectorStatus(profileId).catch(() => null),
        getMem0Status().catch(() => null),
        getSufficiency(profileId).catch(() => null),
        getNuwaStatus().catch(() => null),
        getColleagueStatus().catch(() => null),
        listGeneratedSkills(profileId).catch(() => []),
      ])
      setProfile(p)
      setDocuments(docs)
      setConfigStatus(cfg)
      setMineruStatus(mineru)
      setVectorStatus(vector)
      setMem0Status(mem0)
      setSufficiency(suff)
      setNuwaStatus(nuwa)
      setColleagueStatus(colleague)
      setGeneratedSkills(skills)
    } catch (e: any) {
      setError(`请求人物 ${profileId} 详情失败: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }, [profileId])

  useEffect(() => { fetchData() }, [fetchData])
  useEffect(() => { refreshWebsiteRuns() }, [refreshWebsiteRuns])

  useEffect(() => {
    const el = runtimePromptRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(Math.max(el.scrollHeight, 120), 280)}px`
  }, [runtimePrompt])

  useEffect(() => {
    const hasNuwaRuntime = isRunnableSkill(latestNuwaSkill)
    const hasColleagueRuntime = isRunnableSkill(latestColleagueSkill)
    if (runtimeLabSkillType === 'nuwa' && !hasNuwaRuntime && hasColleagueRuntime) {
      setRuntimeLabSkillType('colleague')
      setRuntimeLabMode('colleague_interaction')
    }
    if (runtimeLabSkillType === 'colleague' && !hasColleagueRuntime && hasNuwaRuntime) {
      setRuntimeLabSkillType('nuwa')
      setRuntimeLabMode('nuwa_thinking')
    }
    if (runtimeLabSkillType === 'compare' && !(hasNuwaRuntime && hasColleagueRuntime)) {
      setRuntimeLabSkillType(hasNuwaRuntime ? 'nuwa' : 'colleague')
      setRuntimeLabMode(hasNuwaRuntime ? 'nuwa_thinking' : 'colleague_interaction')
    }
  }, [
    runtimeLabSkillType,
    latestNuwaSkill?.id,
    latestNuwaSkill?.compatible_skill_generated,
    latestNuwaSkill?.output_path,
    latestColleagueSkill?.id,
    latestColleagueSkill?.compatible_skill_generated,
    latestColleagueSkill?.output_path,
  ])

  useEffect(() => {
    return () => {
      if (pipelineTimerRef.current) window.clearInterval(pipelineTimerRef.current)
      if (pasteHighlightTimerRef.current) window.clearTimeout(pasteHighlightTimerRef.current)
    }
  }, [])

  // Scrollspy for TOC
  useEffect(() => {
    const handleScroll = () => {
      const anchors = document.querySelectorAll('.page-section-anchor')
      let current = ''
      anchors.forEach(el => {
        const rect = el.getBoundingClientRect()
        if (rect.top <= 120) current = el.id
      })
      if (current) setActiveSection(current)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [profile?.latest_portrait])

  useEffect(() => {
    localStorage.setItem('profile-detail-advanced-open-v3', advancedOpen ? 'true' : 'false')
  }, [advancedOpen])

  useEffect(() => {
    const handleHashChange = () => setActiveWorkbenchTab(getInitialWorkbenchTab())
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setPortraitDrawer(null)
        setPreviewDoc(null)
        setEvidenceModal(null)
      }
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        if (activeWorkbenchTab === 'runtime' && runtimePrompt.trim() && !websiteRuntimeRunning) {
          event.preventDefault()
          handleRunWebsiteRuntime()
        }
      }
      if (event.key === '/' && activeWorkbenchTab === 'runtime') {
        const target = event.target as HTMLElement | null
        if (target?.tagName !== 'TEXTAREA' && target?.tagName !== 'INPUT') {
          event.preventDefault()
          runtimePromptRef.current?.focus()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [activeWorkbenchTab, runtimePrompt, websiteRuntimeRunning])

  const selectWorkbenchTab = (tab: WorkbenchTab) => {
    setActiveWorkbenchTab(tab)
    const hash = TAB_TO_HASH[tab]
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${hash}`)
  }

  const scrollToSection = (sectionId: string) => {
    const tab = HASH_TO_TAB[sectionId] || (sectionId === 'overview' ? 'overview' : null)
    if (tab) {
      selectWorkbenchTab(tab)
      document.getElementById('workbench')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      return
    }
    document.getElementById(sectionId)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const allowedExtensions = [
    '.txt', '.md', '.markdown', '.json', '.csv',
    '.pdf', '.docx', '.pptx', '.xlsx', '.png', '.jpg', '.jpeg', '.webp',
  ]
  const mineruExtensions = ['.pdf', '.docx', '.pptx', '.xlsx', '.png', '.jpg', '.jpeg', '.webp']
  const isMineruFile = (name: string) => mineruExtensions.some(ext => name.toLowerCase().endsWith(ext))

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const file = files[0]
    if (!allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext))) {
      setError('不支持的文件格式，请上传 ' + allowedExtensions.join(' / '))
      return
    }
    // Check MinerU requirement for complex files
    if (isMineruFile(file.name)) {
      if (!mineruStatus?.installed) {
        setError(adminView
          ? '当前未安装 MinerU，无法解析 PDF/DOCX/PPTX/XLSX/图片文件。请先运行管理员安装脚本，或上传 txt/md/json/csv 文件。'
          : '当前暂不支持解析复杂文档，请上传 txt / md / json / csv 文件，或联系管理员启用复杂文档解析。'
        )
        return
      }
      if (!mineruStatus?.enabled) {
        setError(adminView ? 'MinerU 已安装但未启用。请在 .env 中设置 MINERU_ENABLED=true' : '复杂文档解析暂未启用，请上传文本资料或联系管理员。')
        return
      }
    }
    try {
      setUploading(true)
      setUploadingFileName(file.name)
      setError('')
      setSuccess('')
      await uploadDocument(profileId, file)
      setSuccess(`文件 "${file.name}" 上传成功`)
      await fetchData()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setUploading(false)
      setUploadingFileName('')
    }
  }

  const highlightPasteComposer = () => {
    setPasteHighlighted(true)
    if (pasteHighlightTimerRef.current) window.clearTimeout(pasteHighlightTimerRef.current)
    pasteHighlightTimerRef.current = window.setTimeout(() => setPasteHighlighted(false), 900)
  }

  const handleReadClipboard = async () => {
    setError('')
    setPasteNotice('')
    if (!navigator.clipboard?.readText) {
      setPasteNotice('当前浏览器不允许直接读取剪贴板，请手动长按粘贴。')
      pasteTextRef.current?.focus()
      return
    }
    try {
      const text = await navigator.clipboard.readText()
      if (!text.trim()) {
        setPasteNotice('剪贴板里暂时没有可读取的文本，请手动粘贴。')
        pasteTextRef.current?.focus()
        return
      }
      setPasteText(text)
      setPasteNotice('已从剪贴板读取文本。')
      highlightPasteComposer()
      requestAnimationFrame(() => pasteTextRef.current?.focus())
    } catch {
      setPasteNotice('当前浏览器不允许直接读取剪贴板，请手动长按粘贴。')
      pasteTextRef.current?.focus()
    }
  }

  const handleClearPastedText = () => {
    setPasteTitle('')
    setPasteText('')
    setPasteNotice('')
    pasteTextRef.current?.focus()
  }

  const handleSavePastedText = async () => {
    const text = pasteText.trim()
    if (!text || pasteSaving) return
    const filename = buildPastedFilename(profileId, pasteTitle)
    try {
      setPasteSaving(true)
      setError('')
      setSuccess('')
      setPasteNotice('')
      await uploadTextAsDocument(profileId, text, filename)
      setSuccess('文本资料已保存')
      setPasteTitle('')
      setPasteText('')
      await fetchData()
    } catch (e: any) {
      setError(e?.message || '保存文本资料失败，请稍后重试。')
    } finally {
      setPasteSaving(false)
    }
  }

  const handlePastedTextKeyDown = (event: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault()
      if (canSavePastedText) handleSavePastedText()
    }
    if (event.key === 'Escape') {
      setPasteNotice('')
      event.currentTarget.blur()
    }
  }

  const startPipelineProgress = () => {
    if (pipelineTimerRef.current) window.clearInterval(pipelineTimerRef.current)
    let cursor = 0
    setPipelineSteps(createPipelineSteps())
    setPipelineSteps(prev => ({ ...prev, parse: 'running' }))
    pipelineTimerRef.current = window.setInterval(() => {
      cursor += 1
      setPipelineSteps(prev => {
        const next = { ...prev }
        PIPELINE_STEPS.forEach((step, index) => {
          if (index < cursor) next[step.key] = 'done'
          if (index === cursor) next[step.key] = 'running'
        })
        return next
      })
      if (cursor >= PIPELINE_STEPS.length - 1 && pipelineTimerRef.current) {
        window.clearInterval(pipelineTimerRef.current)
        pipelineTimerRef.current = null
      }
    }, 900)
  }

  const pipelineStepsFromResult = (result: ProfilePipelineResult): Record<PipelineStepKey, PipelineUiStatus> => {
    if (result.pipeline_status === 'need_upload') {
      return {
        parse: 'warning',
        analysis: 'pending',
        nuwa: 'pending',
        colleague: 'pending',
        runtime: 'pending',
      }
    }
    const analysisStatus = toPipelineUiStatus(result.analysis_status.status)
    const analysisFinished = result.analysis_ready || analysisStatus === 'done' || result.pipeline_status === 'completed' || result.pipeline_status === 'partial'
    const runtimeReadyFromResult = result.runtime_ready
      || result.website_runtime_ready
      || Boolean(result.nuwa_skill_id || result.colleague_skill_id)
    return {
      parse: 'done',
      analysis: analysisStatus,
      nuwa: toPipelineUiStatus(result.nuwa_skill_status.status),
      colleague: toPipelineUiStatus(result.colleague_skill_status.status),
      runtime: runtimeReadyFromResult ? 'done' : analysisFinished ? 'warning' : 'failed',
    }
  }

  const handleAnalyze = async () => {
    let completedResult: ProfilePipelineResult | null = null
    if (!isValidId) {
      setError('当前人物档案 ID 无效')
      setPipelineResult(null)
      setPipelineSteps(createPipelineSteps())
      return
    }
    try {
      setAnalyzing(true)
      setError('')
      setSuccess('')
      setPipelineResult(null)
      console.debug('[Echo Profile] analyze click', {
        currentProfileId: profileId,
        routeProfileId: id,
        pipelineAnalyzeUrl: `/api/profiles/${profileId}/pipeline/analyze`,
      })
      if (pipelineTimerRef.current) {
        window.clearInterval(pipelineTimerRef.current)
        pipelineTimerRef.current = null
      }
      setPipelineSteps({ ...createPipelineSteps(), parse: 'running' })
      const result = await runProfilePipeline(profileId)
      completedResult = result
      setPipelineResult(result)
      if (pipelineTimerRef.current) {
        window.clearInterval(pipelineTimerRef.current)
        pipelineTimerRef.current = null
      }
      setPipelineSteps(pipelineStepsFromResult(result))
      if (result.pipeline_status === 'need_upload') {
        setSuccess(result.next_actions[0] || '请先上传资料后再开始分析。')
      } else if (result.pipeline_status === 'failed') {
        setError(result.errors.join('；') || '分析流水线失败，请检查配置后重试。')
      } else if (result.runtime_ready || result.website_runtime_ready || result.nuwa_skill_id || result.colleague_skill_id) {
        setSuccess('分析完成，模拟实验台已准备好。')
      } else if (result.warnings.length > 0) {
        setSuccess('分析已完成，部分模拟准备存在提示。可展开高级技术详情查看。')
      } else {
        setSuccess('分析完成。')
      }
      await fetchData()
    } catch (e: any) {
      if (pipelineTimerRef.current) {
        window.clearInterval(pipelineTimerRef.current)
        pipelineTimerRef.current = null
      }
      if (completedResult && isNotFoundError(e)) {
        setPipelineSteps(pipelineStepsFromResult(completedResult))
        setSuccess('分析已完成。部分模拟运行历史暂无记录，已按空状态处理。')
      } else if (isNotFoundError(e)) {
        setError('分析接口不存在或当前人物档案不存在。')
        setPipelineSteps({ ...createPipelineSteps(), parse: 'failed' })
      } else {
        setError(e.message)
        setPipelineSteps(prev => {
          const next = { ...prev }
          PIPELINE_STEPS.forEach(step => {
            if (next[step.key] === 'running') next[step.key] = 'failed'
          })
          if (next.analysis !== 'done') next.analysis = 'failed'
          if (next.runtime === 'running') next.runtime = 'warning'
          return next
        })
      }
    } finally {
      if (pipelineTimerRef.current) {
        window.clearInterval(pipelineTimerRef.current)
        pipelineTimerRef.current = null
      }
      setAnalyzing(false)
    }
  }

  const handleExportSkillCard = async () => {
    try {
      setExporting('skill-card')
      setError('')
      const result = await exportSkillCard(profileId)
      const blob = new Blob([result.content], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = result.filename; a.click()
      URL.revokeObjectURL(url)
      setSuccess('风格卡已导出')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setExporting('')
    }
  }

  const handleExportDataset = async () => {
    try {
      setExporting('dataset')
      setError('')
      const result = await exportDataset(profileId)
      const jsonStr = JSON.stringify(result.records, null, 2)
      const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = result.filename; a.click()
      URL.revokeObjectURL(url)
      setSuccess(`数据集已导出，共 ${result.total_records} 条记录`)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setExporting('')
    }
  }

  const handleDeleteDocument = async (docId: number) => {
    try {
      setDeleting(true)
      setError('')
      await deleteDocument(profileId, docId)
      setSuccess('文档已删除')
      setDeletingId(null)
      await fetchData()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setDeleting(false)
    }
  }

  const handlePreviewDocument = async (docId: number) => {
    try {
      setPreviewLoading(true)
      setError('')
      const result = await previewDocument(profileId, docId)
      setPreviewDoc(result)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleRebuildChunks = async () => {
    if (!confirm('确认重建所有文档的文本片段？这不会删除原始文件。')) return
    try {
      setRebuilding(true)
      setError('')
      const result = await rebuildChunks(profileId)
      setSuccess(result.message)
      await fetchData()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRebuilding(false)
    }
  }

  const handleRebuildVectorIndex = async () => {
    try {
      setVectorRebuilding(true)
      setError('')
      setSuccess('')
      const result = await rebuildVectorIndex(profileId)
      if (result.error) {
        setError(result.detail || result.error)
      } else {
        setSuccess(result.detail || `已重建 ${result.indexed} 个向量索引`)
      }
      const vector = await getVectorStatus(profileId).catch(() => null)
      setVectorStatus(vector)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setVectorRebuilding(false)
    }
  }

  const handleExportSFT = async () => {
    try {
      setExporting('sft')
      setError('')
      const result = await exportSFT(profileId)
      const blob = new Blob([result.content], { type: 'application/jsonl;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = result.filename; a.click()
      URL.revokeObjectURL(url)
      setSuccess(`SFT 数据集已导出，共 ${result.total_records} 条训练样本`)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setExporting('')
    }
  }

  const handleExportRAGDataset = async () => {
    try {
      setExporting('rag')
      setError('')
      const result = await exportDataset(profileId)
      const jsonStr = JSON.stringify(result.records, null, 2)
      const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `rag_${result.filename}`; a.click()
      URL.revokeObjectURL(url)
      setSuccess(`RAG 数据集已导出，共 ${result.total_records} 条记录`)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setExporting('')
    }
  }

  const handleExportAnalysisReport = async () => {
    try {
      setExporting('analysis-report')
      setError('')
      const result = await exportAnalysisReport(profileId)
      const blob = new Blob([result.content], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = result.filename; a.click()
      URL.revokeObjectURL(url)
      setSuccess('完整分析报告已导出')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setExporting('')
    }
  }

  const handleShowSkillSpec = async (type: 'nuwa' | 'colleague') => {
    try {
      setError('')
      const spec = type === 'nuwa' ? await getNuwaSpec() : await getColleagueSpec()
      setSkillSpec(spec)
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleGenerateSkill = async (type: 'nuwa' | 'colleague') => {
    try {
      setGeneratingSkill(type)
      setError('')
      setSuccess('')
      const result = type === 'nuwa'
        ? await generateNuwaSkill(profileId)
        : await generateColleagueSkill(profileId)
      if (result.error || !result.generated) {
        setError(result.detail || result.error || 'Skill 生成失败')
      } else {
        setSuccess(result.detail || 'Skill 包已生成')
      }
      const skills = await listGeneratedSkills(profileId).catch(() => [])
      setGeneratedSkills(skills)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setGeneratingSkill('')
    }
  }

  const refreshGeneratedSkills = async () => {
    const skills = await listGeneratedSkills(profileId).catch(() => [])
    setGeneratedSkills(skills)
  }

  const handleValidateSkill = async (skill?: GeneratedSkill) => {
    if (!skill) return
    try {
      setValidatingSkill(skill.id)
      setError('')
      const result = await validateGeneratedSkill(profileId, skill.id)
      if (result.errors.length > 0) {
        setError(`结构验证完成：${result.validation_score}/100，存在 ${result.errors.length} 个错误`)
      } else {
        setSuccess(`结构验证通过：${result.validation_score}/100`)
      }
      await refreshGeneratedSkills()
    } catch (e: any) {
      if (isNotFoundError(e)) {
        setSuccess('当前 Skill 暂无结构验证记录。请先生成或刷新 Skill 包。')
      } else {
        setError(e.message)
      }
    } finally {
      setValidatingSkill(null)
    }
  }

  const handleDryRunSkill = async (skill?: GeneratedSkill) => {
    if (!skill) return
    try {
      setDryRunningSkill(skill.id)
      setError('')
      const result = await dryRunGeneratedSkill(profileId, skill.id)
      setDryRunResult(result)
      if (result.runtime_simulated) {
        setSuccess('Dry-run 模拟运行完成：runtime_simulated=true，actual_runtime_invoked=false')
      } else {
        setError(result.error || 'Dry-run 未完成，可能是 LLM provider 不可用')
      }
      await refreshGeneratedSkills()
    } catch (e: any) {
      if (isNotFoundError(e)) {
        setSuccess('当前 Skill 暂无 Dry-run 记录。请先生成或刷新 Skill 包。')
      } else {
        setError(e.message)
      }
    } finally {
      setDryRunningSkill(null)
    }
  }

  const handleInstallInstructions = async (skill?: GeneratedSkill) => {
    if (!skill) return
    try {
      setInstallingSkill(skill.id)
      setError('')
      const result = await getSkillInstallInstructions(profileId, skill.id, 'codex')
      if (result.install_instructions_path) {
        setSuccess('安装说明已生成，并会随 ZIP 一起下载')
      }
      await refreshGeneratedSkills()
    } catch (e: any) {
      if (isNotFoundError(e)) {
        setSuccess('未生成安装说明。请先确认 Skill 包已生成。')
      } else {
        setError(e.message)
      }
    } finally {
      setInstallingSkill(null)
    }
  }

  const handleGenerateRuntimeCases = async (skill?: GeneratedSkill) => {
    if (!skill) return
    try {
      setRuntimeBusySkill(skill.id)
      setError('')
      const result = await generateRuntimeTestCases(profileId, skill.id, 'codex')
      setRuntimeCases(result)
      setSuccess('Runtime 测试用例已生成，并会随 ZIP 一起下载')
    } catch (e: any) {
      if (isNotFoundError(e)) {
        setSuccess('未生成测试用例。请先确认 Skill 包已生成。')
      } else {
        setError(e.message)
      }
    } finally {
      setRuntimeBusySkill(null)
    }
  }

  const handleViewRuntimeCases = async (skill?: GeneratedSkill) => {
    if (!skill) return
    try {
      setRuntimeBusySkill(skill.id)
      setError('')
      const result = await getRuntimeTestCases(profileId, skill.id, runtimeForm.runtime_target || 'codex')
      setRuntimeCases(result)
    } catch (e: any) {
      if (isNotFoundError(e)) {
        setRuntimeCases({
          runtime_target: runtimeForm.runtime_target || 'codex',
          markdown_path: '',
          json_path: '',
          test_cases: [],
          warnings: ['未生成测试用例'],
        })
        setSuccess('未生成测试用例，已显示为空状态。')
      } else {
        setError(e.message)
      }
    } finally {
      setRuntimeBusySkill(null)
    }
  }

  const handleOpenRuntimeResult = (skill?: GeneratedSkill) => {
    if (!skill) return
    setRuntimeModalSkill(skill)
    setRuntimeEvaluation(null)
    setRuntimeForm({
      runtime_target: skill.l5c_runtime_target || 'codex',
      tester_note: '',
      test_output_text: '',
      evidence_of_runtime: '',
    })
  }

  const handleSubmitRuntimeResult = async (evaluate: boolean) => {
    if (!runtimeModalSkill) return
    try {
      setRuntimeBusySkill(runtimeModalSkill.id)
      setError('')
      if (evaluate) {
        const result = await evaluateRuntimeResult(profileId, runtimeModalSkill.id, runtimeForm)
        setRuntimeEvaluation(result)
        setSuccess(result.can_mark_l5c ? '外部 runtime 结果评估通过：已记录 L5c' : '运行结果已评估，但尚未达到 L5c')
        await refreshGeneratedSkills()
      } else {
        await submitRuntimeResult(profileId, runtimeModalSkill.id, runtimeForm)
        setSuccess('外部 runtime 输出已回填，尚未评估')
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRuntimeBusySkill(null)
    }
  }

  const handleRunWebsiteRuntime = async () => {
    const prompt = runtimePrompt.trim()
    if (!prompt) {
      setError('请输入要测试 Skill 的问题或场景。')
      return
    }
    try {
      setWebsiteRuntimeRunning(true)
      setError('')
      setSuccess('')
      setRuntimeTraceOpen(false)
      setFeedbackExpanded(false)
      setFeedbackNote('')
      setFeedbackRating('good')
      setWebsiteRuntimeResult(null)
      setCompareRuntimeResult(null)

      if (runtimeLabSkillType === 'compare') {
        if (!isRunnableSkill(latestNuwaSkill) || !isRunnableSkill(latestColleagueSkill)) {
        setError('对比模拟需要同时准备思维模拟和互动模拟。')
          return
        }
        setRuntimeBusySkill(latestNuwaSkill.id)
        const result = await compareWebsiteSkills(profileId, {
          user_prompt: prompt,
          nuwa_skill_id: latestNuwaSkill.id,
          colleague_skill_id: latestColleagueSkill.id,
        })
        setCompareRuntimeResult(result)
        setWebsiteRuntimeResult(null)
        setWebsiteRuns(prev => ({
          ...prev,
          [latestNuwaSkill.id]: [result.nuwa_result, ...(prev[latestNuwaSkill.id] || [])].slice(0, 30),
          [latestColleagueSkill.id]: [result.colleague_result, ...(prev[latestColleagueSkill.id] || [])].slice(0, 30),
        }))
        setSuccess('对比模拟已完成。')
        await refreshWebsiteRuns()
        return
      }

      const skill = runtimeLabSkillType === 'nuwa' ? latestNuwaSkill : latestColleagueSkill
      if (!isRunnableSkill(skill)) {
        setError(`请先准备${runtimeLabSkillType === 'nuwa' ? '思维模拟' : '互动模拟'}能力。`)
        return
      }
      setRuntimeBusySkill(skill.id)
      const effectiveMode: SkillRuntimeMode =
        runtimeLabMode === 'compare'
          ? (runtimeLabSkillType === 'nuwa' ? 'nuwa_thinking' : 'colleague_interaction')
          : runtimeLabMode
      const result = await runWebsiteSkill(profileId, skill.id, {
        user_prompt: prompt,
        runtime_mode: effectiveMode,
      })
      setWebsiteRuntimeResult(result)
      setCompareRuntimeResult(null)
      setWebsiteRuns(prev => ({
        ...prev,
        [skill.id]: [result, ...(prev[skill.id] || []).filter(item => item.id !== result.id)].slice(0, 30),
      }))
      if (result.status === 'error') {
        setError('模拟运行失败，请查看高级技术详情。')
      } else if (result.status === 'blocked') {
        setSuccess('站内模拟已完成安全边界拦截。')
      } else {
        setSuccess('站内模拟运行完成。')
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setWebsiteRuntimeRunning(false)
      setRuntimeBusySkill(null)
    }
  }

  const handleClearWebsiteRuntime = () => {
    setRuntimePrompt('')
    setWebsiteRuntimeResult(null)
    setCompareRuntimeResult(null)
    setRuntimeTraceOpen(false)
    setFeedbackNote('')
    setFeedbackRating('good')
    setFeedbackExpanded(false)
  }

  const handleRuntimeExamplePrompt = (prompt: string) => {
    setRuntimePrompt(prompt)
    if (prompt.includes('两个模拟视角') || prompt.includes('两个引擎')) {
      if (isRunnableSkill(latestNuwaSkill) && isRunnableSkill(latestColleagueSkill)) {
        setRuntimeLabSkillType('compare')
        setRuntimeLabMode('compare')
      } else {
        setError('对比模拟需要同时准备思维模拟和互动模拟。')
      }
    } else if (runtimeLabSkillType === 'compare') {
      setRuntimeLabSkillType(isRunnableSkill(latestNuwaSkill) ? 'nuwa' : 'colleague')
      setRuntimeLabMode(isRunnableSkill(latestNuwaSkill) ? 'nuwa_thinking' : 'colleague_interaction')
    }
  }

  const handleCopyWebsiteAnswer = (result?: SkillWebsiteRun | null) => {
    const target = result || websiteRuntimeResult
    if (!target?.answer) return
    navigator.clipboard.writeText(target.answer).then(() => {
      setCopied('website-runtime-answer')
      setTimeout(() => setCopied(''), 2000)
    })
  }

  const handleOpenRecentWebsiteRun = (run: SkillWebsiteRun) => {
    setWebsiteRuntimeResult(run)
    setCompareRuntimeResult(null)
    setRuntimeTraceOpen(false)
  }

  const handleSubmitWebsiteFeedback = async () => {
    if (!websiteRuntimeResult?.id) return
    try {
      setFeedbackBusy(true)
      setError('')
      const result = await submitWebsiteSkillRunFeedback(
        profileId,
        websiteRuntimeResult.generated_skill_id,
        websiteRuntimeResult.id,
        { rating: feedbackRating, note: feedbackNote },
      )
      setSuccess(
        result.correction_history_appended
          ? '反馈已记录到修正历史，暂不会自动改写模拟能力。'
          : '反馈已记录。'
      )
      setFeedbackNote('')
      setFeedbackRating('good')
      setFeedbackExpanded(false)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setFeedbackBusy(false)
    }
  }

  // Map portrait section index → evidence module key
  // Module 1 (人物摘要) → "1", Module 3 (语言风格) → "3", etc.
  const getEvidenceForSection = (sectionTitle: string): EvidenceModule | null => {
    const match = sectionTitle.match(/^(\d+)\./)
    if (!match) return null
    const key = match[1]
    return evidenceMap[key] || null
  }

  const handleCopyStyleCard = () => {
    if (profile?.latest_style_card) {
      navigator.clipboard.writeText(profile.latest_style_card).then(() => {
        setCopied('style-card')
        setTimeout(() => setCopied(''), 2000)
      })
    }
  }

  // Guards
  if (!isValidId) {
    return (
      <div>
        <div className="alert alert-error">
          <p><strong>无效的人物 ID</strong></p>
          <p>当前 URL 中的 ID 为: <code>{id || '(空)'}</code>，不是有效的人物 ID。</p>
        </div>
        <div style={{ marginTop: '1rem' }}>
          <Link to="/profiles" className="btn-primary">返回人物列表</Link>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div>
        <div className="empty-state">
          <div className="spinner" style={{ margin: '0 auto' }} />
          <p style={{ marginTop: '0.5rem' }}>加载人物 {profileId} 详情中...</p>
        </div>
      </div>
    )
  }

  if (error && !profile) {
    return (
      <div>
        <div className="alert alert-error">
          <p><strong>加载失败</strong></p>
          <p>人物 ID: {profileId}</p>
          <p>{error}</p>
        </div>
        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
          <button className="btn-primary" onClick={fetchData}>重试</button>
          <Link to="/profiles" className="btn-primary" style={{ background: 'var(--c-text-muted)', borderColor: 'var(--c-text-muted)' }}>返回人物列表</Link>
        </div>
      </div>
    )
  }

  if (!profile) {
    return (
      <div>
        <div className="alert alert-error">
          <p><strong>人物档案不存在</strong></p>
          <p>人物 ID {profileId} 在后端数据库中未找到，可能已被删除。</p>
        </div>
        <div style={{ marginTop: '1rem' }}>
          <Link to="/profiles" className="btn-primary">返回人物列表</Link>
        </div>
      </div>
    )
  }

  const portraitSections = parseMarkdownSections(profile.latest_portrait || '').filter(section => /^\d+\./.test(section.title))
  const styleSections = parseStyleCardSections(profile.latest_style_card || '')
  const coverage = profile.analysis_quality?.evidence_coverage ?? 0
  const avgConfidence = profile.analysis_quality?.avg_confidence ?? 0
  const portraitItems = portraitSections.map(section => {
    const evidence = getEvidenceForSection(section.title)
    const moduleNo = (section.title.match(/^(\d+)\./) || ['', ''])[1]
    const claimCount = evidence?.claims?.length || 0
    const avgClaimConfidence = claimCount
      ? Math.round(evidence!.claims.reduce((sum, claim) => sum + (claim.confidence_score || 0), 0) / claimCount)
      : null
    return {
      section,
      evidence,
      moduleNo,
      claimCount,
      avgClaimConfidence,
      title: section.title.replace(/^\d+\.\s*/, ''),
      summary: summarizeEvidenceModule(evidence, section.content),
    }
  })
  const filteredPortraitItems = portraitItems.filter(item => {
    if (portraitFilter === 'evidence') return Boolean(item.evidence)
    if (portraitFilter === 'insufficient') return Boolean(item.evidence && !item.evidence.data_sufficient)
    if (portraitFilter === 'high') return item.avgClaimConfidence !== null && item.avgClaimConfidence >= 75
    if (portraitFilter === 'low') return item.avgClaimConfidence !== null && item.avgClaimConfidence < 60
    return true
  })
  const selectedRuntimeSkill = runtimeLabSkillType === 'nuwa'
    ? latestNuwaSkill
    : runtimeLabSkillType === 'colleague'
      ? latestColleagueSkill
      : undefined
  const nuwaRunnable = isRunnableSkill(latestNuwaSkill)
  const colleagueRunnable = isRunnableSkill(latestColleagueSkill)
  const selectedRuntimeRuns = selectedRuntimeSkill ? (websiteRuns[selectedRuntimeSkill.id] || []) : []
  const canRunWebsiteRuntime = runtimeLabSkillType === 'compare'
    ? Boolean(nuwaRunnable && colleagueRunnable)
    : isRunnableSkill(selectedRuntimeSkill)
  const simulationReady = Boolean(
    nuwaRunnable
    || colleagueRunnable
    || pipelineResult?.runtime_ready
    || pipelineResult?.website_runtime_ready
    || pipelineResult?.nuwa_skill_id
    || pipelineResult?.colleague_skill_id
  )
  const overviewChecklist = [
    { label: '资料已上传', done: profile.document_count > 0 },
    { label: '画像已生成', done: profile.has_analysis },
    { label: '模拟已准备', done: simulationReady },
    { label: '可导出报告', done: profile.has_analysis },
  ]
  const nextStepSuggestion = profile.document_count === 0
    ? '先上传授权资料。'
    : !profile.has_analysis
      ? '点击开始分析，生成证据化画像。'
      : !simulationReady
        ? '重新分析以准备模拟实验台。'
        : '可以进入模拟实验台或导出完整报告。'
  const selectedEngineStatus = runtimeLabSkillType === 'nuwa'
    ? nuwaStatus
    : runtimeLabSkillType === 'colleague'
      ? colleagueStatus
      : null
  const hasGeneratedWebsiteSkill = Boolean(nuwaRunnable || colleagueRunnable)
  const activeEngineLabel = skillTypeLabel(runtimeLabSkillType)
  const activeSourceRepo = runtimeLabSkillType === 'compare'
    ? `${nuwaStatus?.source_path || defaultSourceRepo('nuwa')} / ${colleagueStatus?.source_path || defaultSourceRepo('colleague')}`
    : selectedEngineStatus?.source_path || defaultSourceRepo(runtimeLabSkillType === 'colleague' ? 'colleague' : 'nuwa')
  const loadedSkillFiles = runtimeLabSkillType === 'compare'
    ? `${latestNuwaSkill?.generated_files?.length || 0} + ${latestColleagueSkill?.generated_files?.length || 0}`
    : String(selectedRuntimeSkill?.generated_files?.length || websiteRuntimeResult?.files_used?.length || 0)
  const llmProviderLabel = configStatus
    ? (configStatus.is_mock ? 'Mock' : (configStatus.llm_provider || 'OpenAI-compatible'))
    : 'Unknown'
  const evidenceSourceLabel = vectorStatus?.available
    ? 'Qdrant vector / SQLite chunks'
    : 'SQLite chunks / 基础检索'
  const externalRuntimeLabel = runtimeLabSkillType === 'compare'
    ? 'Not invoked / L5c pending'
    : selectedRuntimeSkill?.l5c_passed
      ? `${selectedRuntimeSkill.l5c_runtime_target || 'external'} / L5c`
      : 'Not invoked / L5c pending'

  return (
    <div className={`profile-detail-page workbench-page tab-${activeWorkbenchTab} ${adminView ? 'admin-view' : 'public-view'} fade-in`}>
      <div id="workbench" className="profile-app-shell page-section-anchor">
        <aside className="profile-sidebar">
          <div className="profile-sidebar-card">
            <span className={simulationReady ? 'badge badge-success' : 'badge badge-muted'}>
              {simulationReady ? '模拟可用' : '待准备'}
            </span>
            <strong>{profile.name}</strong>
            <p>{profile.document_count} 文件 · {profile.chunk_count} 片段</p>
          </div>
          <PageMiniNav
            items={WORKBENCH_TABS.map(item => ({ id: item.id, label: item.label, hint: item.hint }))}
            activeSection={activeWorkbenchTab}
            onSelect={id => selectWorkbenchTab(id as WorkbenchTab)}
          />
          <div className="profile-sidebar-note">
            技术诊断、依赖状态和底层调试信息已隐藏。
          </div>
        </aside>
        <div className="profile-main">
      {/* ── Header Card ── */}
      <div id="overview" className="profile-header-card page-section-anchor page-overview-section">
        <div>
          <div className="header-meta">
            <span className="badge badge-info">档案 #{profile.id}</span>
            <span className="badge">{relationshipLabel(profile.relationship_type)}</span>
            <span className={profile.has_analysis ? 'badge badge-success' : 'badge badge-muted'}>
              {profile.has_analysis ? '已生成画像' : '待分析'}
            </span>
          </div>
          <h1>{profile.name}</h1>
          <p className="header-description">{profile.description || '暂无描述。上传资料后可生成证据化人物画像。'}</p>
          <div className="status-row">
            <span className={simulationReady ? 'badge badge-success' : 'badge badge-warning'}>
              模拟 · {simulationReady ? '已准备' : '未准备'}
            </span>
            <span className={profile.has_analysis ? 'badge badge-success' : 'badge badge-muted'}>
              画像 · {profile.has_analysis ? '已完成' : '待生成'}
            </span>
          </div>
          <div className="header-actions">
            <button
              className="btn-primary"
              onClick={handleAnalyze}
              disabled={analyzing || profile.chunk_count === 0}
            >
              {analyzing ? <><span className="spinner" /> 分析准备中</> : profile.has_analysis ? '重新分析' : '开始分析'}
            </button>
            <button className="btn-secondary" onClick={() => scrollToSection('runtime')}>进入模拟实验台</button>
          </div>
        </div>
        <div>
          <div className="profile-metrics-grid">
            <QualityMetric label="文件数" value={String(profile.document_count)} />
            <QualityMetric label="chunk 数" value={String(profile.chunk_count)} />
            <QualityMetric label="证据覆盖率" value={`${coverage}%`} />
            <QualityMetric label="模拟状态" value={simulationReady ? '已准备' : '未准备'} />
          </div>
          <details className="profile-more-metrics">
            <summary>更多指标</summary>
            <div className="quality-grid compact-quality-grid">
              <QualityMetric label="资料字数" value={(profile.total_chars || 0).toLocaleString()} />
              <QualityMetric label="平均置信度" value={String(avgConfidence)} />
              <QualityMetric label="最近更新" value={formatDate(profile.updated_at || profile.created_at)} />
              <QualityMetric label="资料充分度" value={sufficiency ? sufficiency.label : '待评估'} />
            </div>
          </details>
        </div>
      </div>

      {error && <div className="alert alert-error" style={{ cursor: 'pointer' }} onClick={() => setError('')}>{error} (点击关闭)</div>}
      {success && <div className="alert alert-success" style={{ cursor: 'pointer' }} onClick={() => setSuccess('')}>{success} (点击关闭)</div>}

      <div className="mobile-action-bar" aria-label="快速操作">
        <button className="btn-secondary" onClick={handleAnalyze} disabled={analyzing || profile.chunk_count === 0}>
          分析
        </button>
        <button className="btn-secondary" onClick={() => selectWorkbenchTab('runtime')}>
          模拟
        </button>
        <button className="btn-primary" onClick={handleExportAnalysisReport} disabled={!profile.has_analysis || exporting === 'analysis-report'}>
          导出
        </button>
      </div>

      <section className="card workbench-panel overview-panel page-overview-panel">
        <div className="section-title" style={{ marginTop: 0 }}>
          <div>
            <h2>工作台总览</h2>
            <p>只展示当前档案最重要的状态和下一步动作。</p>
          </div>
          <span className={simulationReady ? 'badge badge-success' : 'badge badge-muted'}>
            {simulationReady ? '模拟可用' : '模拟未准备'}
          </span>
        </div>
        <div className="overview-grid">
          <div className="compact-card overview-status-card">
            <span className={profile.has_analysis ? 'badge badge-success' : 'badge badge-warning'}>
              {profile.has_analysis ? '分析完成' : '待分析'}
            </span>
            <h3>{profile.has_analysis ? '证据化画像已生成' : '还没有生成画像'}</h3>
            <p>{nextStepSuggestion}</p>
            <div className="overview-actions">
              <button className="btn-primary" onClick={handleAnalyze} disabled={analyzing || profile.chunk_count === 0}>
                {profile.has_analysis ? '重新分析' : '开始分析'}
              </button>
              <button className="btn-secondary" onClick={() => selectWorkbenchTab('runtime')}>进入模拟</button>
            </div>
          </div>
          <div className="overview-metrics">
            <QualityMetric label="资料充分度" value={sufficiency ? sufficiency.label : '待评估'} />
            <QualityMetric label="证据覆盖率" value={`${coverage}%`} />
            <QualityMetric label="平均置信度" value={String(avgConfidence)} />
            <QualityMetric label="文件 / 片段" value={`${profile.document_count} / ${profile.chunk_count}`} />
          </div>
          <div className="compact-card checklist-card">
            <h3>准备情况</h3>
            <div className="compact-checklist">
              {overviewChecklist.map(item => (
                <span key={item.label} className={item.done ? 'done' : ''}>
                  <b>{item.done ? '✓' : '·'}</b>{item.label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {(analyzing || pipelineResult) && (
        <PipelinePanel
          hasAnalysis={profile.has_analysis}
          chunkCount={profile.chunk_count}
          analyzing={analyzing}
          steps={pipelineSteps}
          result={pipelineResult}
          simulationReady={simulationReady}
          onRun={handleAnalyze}
        />
      )}

      <div id="advanced" className="page-section-anchor page-advanced-anchor" />

      {/* ── Retrieval Engine Card ── */}
      {adminView && vectorStatus && (
        <details
          className="card retrieval-card advanced-tech-details page-advanced-section"
          style={{ marginBottom: '1.5rem' }}
          open={advancedOpen}
          onToggle={e => setAdvancedOpen(e.currentTarget.open)}
        >
          <summary>
            <div>
              <strong>高级检索详情</strong>
              <span>管理员 / 高级用户查看当前证据检索方式、embedding 模型和向量索引状态。</span>
            </div>
            <em>{vectorStatus.available ? '语义检索增强' : '基础检索'}</em>
          </summary>
          <div className="advanced-tech-body">
          <div className="section-title" style={{ marginTop: 0 }}>
            <div>
              <h2>检索引擎状态</h2>
              <p>
                {vectorStatus.available
                  ? '当前使用语义检索增强证据命中，并保留基础检索作为兜底。'
                  : '当前使用基础检索。资料量较大时，管理员可启用语义检索增强证据命中。'}
              </p>
            </div>
            <span className={vectorStatus.available ? 'badge badge-success' : 'badge badge-muted'}>
              {vectorStatus.available ? '语义检索增强' : '基础检索'}
            </span>
          </div>
          <div className="quality-grid">
            <QualityMetric label="当前检索" value={vectorStatus.available ? '语义增强 + 基础兜底' : '基础检索'} />
            <QualityMetric label="语义增强" value={vectorStatus.available ? '已启用' : '管理员可选'} />
            <QualityMetric label="Embedding" value={vectorStatus.available ? (vectorStatus.embedding_model || '已配置') : '管理员可配置'} />
            <QualityMetric label="索引状态" value={vectorStatus.available ? `${vectorStatus.points_count || 0} points` : '未启用'} />
          </div>
          <div className="subtle-panel retrieval-note">
            <div>
              <strong>{vectorStatus.available ? '语义检索已启用' : '基础检索正常可用'}</strong>
              <p>
                {vectorStatus.available
                  ? '证据检索会优先参考语义相似度，并控制返回片段数量。'
                  : '未启用语义增强时，系统会继续使用基础检索，不影响画像和模拟主流程。'}
              </p>
              {!vectorStatus.available && (vectorStatus.detail || vectorStatus.error) && (
                <details className="admin-diagnostics">
                  <summary>管理员诊断信息</summary>
                  {vectorStatus.detail && <p>{vectorStatus.detail}</p>}
                  {vectorStatus.error && <p>{vectorStatus.error}</p>}
                </details>
              )}
            </div>
            <button
              className="btn-secondary"
              onClick={handleRebuildVectorIndex}
              disabled={vectorRebuilding || !vectorStatus.installed || !vectorStatus.enabled || profile.chunk_count === 0}
            >
              {vectorRebuilding ? <><span className="spinner" /> 重建中</> : '重建向量索引'}
            </button>
          </div>
          </div>
        </details>
      )}

      {/* ── Advanced Technical Details ── */}
      {adminView && <details
        className="card skill-foundry-card advanced-tech-details page-advanced-section"
        style={{ marginBottom: '1.5rem' }}
        open={advancedOpen}
        onToggle={e => setAdvancedOpen(e.currentTarget.open)}
      >
        <summary>
          <div>
            <strong>高级技术详情</strong>
            <span>管理员 / 高级用户查看 GitHub Skill 引擎、结构验证、dry-run、外部 L5c 回填和 ZIP 安装信息。</span>
          </div>
          <em>默认折叠</em>
        </summary>
        <div className="advanced-tech-body">
        <div className="section-title" style={{ marginTop: 0 }}>
          <div>
            <h2>Persona Skill Foundry</h2>
            <p>外部 GitHub Skill 契约被导入、解析、生成，并可在站内 Website Runtime Lab 中真实运行。</p>
          </div>
          <span className="badge badge-info">Skill 蒸馏引擎</span>
        </div>
        <div className="subtle-panel skill-boundary-note">
          当前阶段只生成兼容文件包，不调用外部仓库的采集器、宿主安装器或不稳定 CLI。
          生成包不包含原始上传文件、数据库、API Key 或 .env。
        </div>
        <div className="quality-grid advanced-service-grid">
          <QualityMetric label="LLM Provider" value={llmProviderLabel} />
          <QualityMetric label="MinerU" value={mineruStatus?.installed && mineruStatus.enabled ? '可用' : '未启用'} />
          <QualityMetric label="语义检索增强" value={vectorStatus?.available ? '已启用' : '管理员可选'} />
          <QualityMetric label="mem0" value={mem0Status?.available ? '可用' : mem0Status?.enabled ? '已启用未可用' : '可选未启用'} />
        </div>

        <SkillFoundryLayer
          index="01"
          title="Engine Status"
          description="外部仓库导入、契约解析、Skill 生成、站内运行与外部 L5c 状态分开展示。"
        >
          <div className="skill-engine-grid">
            <SkillEngineCard
              title="Nuwa Skill Engine"
              subtitle="心智模型 / 决策启发式 / 表达 DNA"
              status={nuwaStatus}
              generated={latestNuwaSkill}
              runtimeRuns={latestNuwaSkill ? (websiteRuns[latestNuwaSkill.id] || []) : []}
            />
            <SkillEngineCard
              title="Colleague Skill Engine"
              subtitle="Persona + Work 双层结构"
              status={colleagueStatus}
              generated={latestColleagueSkill}
              runtimeRuns={latestColleagueSkill ? (websiteRuns[latestColleagueSkill.id] || []) : []}
            />
          </div>
          {!profile.has_analysis && (
            <p className="skill-layer-note">需要先生成画像报告和风格卡，才能蒸馏为外部 Skill 兼容包。</p>
          )}
        </SkillFoundryLayer>

        <SkillFoundryLayer
          index="02"
          title="Skill Package"
          description="生成、查看、验证、dry-run、安装说明和 ZIP 下载属于文件包工作流；它还不是站内运行。"
        >
          <div className="skill-package-grid">
            <SkillPackageCard
              title="Nuwa Package"
              generated={latestNuwaSkill}
              disabled={!profile.has_analysis || generatingSkill === 'nuwa'}
              loading={generatingSkill === 'nuwa'}
              validating={validatingSkill === latestNuwaSkill?.id}
              dryRunning={dryRunningSkill === latestNuwaSkill?.id}
              installing={installingSkill === latestNuwaSkill?.id}
              runtimeBusy={runtimeBusySkill === latestNuwaSkill?.id}
              onSpec={() => handleShowSkillSpec('nuwa')}
              onGenerate={() => handleGenerateSkill('nuwa')}
              onValidate={() => handleValidateSkill(latestNuwaSkill)}
              onDryRun={() => handleDryRunSkill(latestNuwaSkill)}
              onInstallInstructions={() => handleInstallInstructions(latestNuwaSkill)}
              onGenerateRuntimeCases={() => handleGenerateRuntimeCases(latestNuwaSkill)}
              onViewRuntimeCases={() => handleViewRuntimeCases(latestNuwaSkill)}
              onOpenRuntimeResult={() => handleOpenRuntimeResult(latestNuwaSkill)}
              onDownload={() => latestNuwaSkill && (window.location.href = generatedSkillDownloadUrl(profileId, latestNuwaSkill.id))}
            />
            <SkillPackageCard
              title="Colleague Package"
              generated={latestColleagueSkill}
              disabled={!profile.has_analysis || generatingSkill === 'colleague'}
              loading={generatingSkill === 'colleague'}
              validating={validatingSkill === latestColleagueSkill?.id}
              dryRunning={dryRunningSkill === latestColleagueSkill?.id}
              installing={installingSkill === latestColleagueSkill?.id}
              runtimeBusy={runtimeBusySkill === latestColleagueSkill?.id}
              onSpec={() => handleShowSkillSpec('colleague')}
              onGenerate={() => handleGenerateSkill('colleague')}
              onValidate={() => handleValidateSkill(latestColleagueSkill)}
              onDryRun={() => handleDryRunSkill(latestColleagueSkill)}
              onInstallInstructions={() => handleInstallInstructions(latestColleagueSkill)}
              onGenerateRuntimeCases={() => handleGenerateRuntimeCases(latestColleagueSkill)}
              onViewRuntimeCases={() => handleViewRuntimeCases(latestColleagueSkill)}
              onOpenRuntimeResult={() => handleOpenRuntimeResult(latestColleagueSkill)}
              onDownload={() => latestColleagueSkill && (window.location.href = generatedSkillDownloadUrl(profileId, latestColleagueSkill.id))}
            />
          </div>
        </SkillFoundryLayer>

        <SkillFoundryLayer
          index="03"
          title="Website Runtime Technical Trace"
          description="这里只展示运行来源、文件加载和最近运行摘要；完整回答保留在主模拟实验台。"
        >
          <section className="skill-runtime-lab advanced-runtime-summary">
            <RuntimeProvenancePanel
              activeEngine={activeEngineLabel}
              sourceRepo={activeSourceRepo}
              skillFilesLoaded={loadedSkillFiles}
              llmProvider={llmProviderLabel}
              evidenceSource={evidenceSourceLabel}
              externalRuntime={externalRuntimeLabel}
            />

            {!hasGeneratedWebsiteSkill ? (
              <div className="runtime-empty-state subtle-panel">
                <span className="badge badge-muted">waiting for skill package</span>
                <h4>还没有生成 Skill 包</h4>
                <p>请先在上方生成 Nuwa 或 Colleague Skill，然后再进行站内运行。</p>
              </div>
            ) : (
              <div className="recent-runs-list">
                <div className="recent-runs-head">
                  <strong>Recent Website Runs</strong>
                  <span>{runtimeLabSkillType === 'compare' ? '按单引擎查看' : `${selectedRuntimeRuns.length} runs`}</span>
                </div>
                {runtimeLabSkillType !== 'compare' && selectedRuntimeRuns.length > 0 ? (
                  <div className="recent-run-items">
                    {selectedRuntimeRuns.slice(0, 8).map(run => (
                      <button key={run.id || `${run.created_at}-${run.runtime_mode}`} onClick={() => handleOpenRecentWebsiteRun(run)}>
                        <span className={runtimeStatusBadgeClass(run.status)}>{run.status}</span>
                        <strong>{runtimeModeLabel(run.runtime_mode)}</strong>
                        <em>{formatDateTime(run.created_at)}</em>
                      </button>
                    ))}
                  </div>
                ) : (
                  <p>{runtimeLabSkillType === 'compare' ? 'Compare 会产生两条单独运行记录，可切回 Nuwa 或 Colleague 查看。' : '还没有站内运行记录。'}</p>
                )}
              </div>
            )}
          </section>
        </SkillFoundryLayer>

        <SkillFoundryLayer
          index="04"
          title="Feedback & Correction"
          description="运行反馈记录到 correction history，用于后续人工修正；不会自动重写 Skill，也不会伪造 L5c。"
        >
          <div className="feedback-correction-grid">
            <div className="subtle-panel correction-status-panel">
              <span className="badge badge-muted">feedback signals</span>
              <h4>运行结果下方可提交反馈</h4>
              <p>支持 good / inaccurate / unsafe / not_like_person / missing_evidence。负向反馈会展开说明输入框。</p>
            </div>
            <div className="subtle-panel correction-status-panel">
              <span className="badge badge-info">correction_history.md</span>
              <h4>反馈已记录后不会立即改写包</h4>
              <p>系统只沉淀修正线索；Skill 文件更新仍由用户主动重新生成或人工审阅触发。</p>
            </div>
          </div>
        </SkillFoundryLayer>
        </div>
      </details>}

      {/* ── Analysis Quality Card ── */}
      {profile.analysis_quality && (
        <details className="card page-summary-section quality-disclosure" style={{ marginBottom: '1.5rem' }}>
          <summary>
            <div>
              <strong>更多分析指标</strong>
              <span>字数、多样性、语料类型等辅助指标，默认折叠。</span>
            </div>
            <span className={simulationReady ? 'badge badge-success' : 'badge badge-warning'}>
              {simulationReady ? '模拟已准备' : '等待模拟准备'}
            </span>
          </summary>
          <div className="quality-grid">
            <QualityMetric label="资料字数" value={profile.analysis_quality.total_chars.toLocaleString()} />
            <QualityMetric label="文档数量" value={String(profile.analysis_quality.document_count)} />
            <QualityMetric label="片段数量" value={String(profile.analysis_quality.chunk_count)} />
            <QualityMetric label="证据覆盖率" value={`${profile.analysis_quality.evidence_coverage}%`} />
            <QualityMetric label="平均置信度" value={`${profile.analysis_quality.avg_confidence}`} />
            <QualityMetric label="多样性评分" value={`${profile.analysis_quality.diversity_score}/100`} />
            <QualityMetric label="聊天语料" value={profile.analysis_quality.has_chat_corpus ? '是' : '否'} />
            <QualityMetric label="包含长文" value={profile.analysis_quality.has_long_text ? '是' : '否'} />
            <QualityMetric label="多情绪场景" value={profile.analysis_quality.has_multi_emotion ? '是' : '否'} />
          </div>
        </details>
      )}

      <section id="runtime" className="card simplified-runtime-card page-section-anchor page-runtime-section" style={{ marginBottom: '1.5rem' }}>
        <div className="section-title" style={{ marginTop: 0 }}>
          <div>
            <h2>模拟实验台</h2>
            <p>选择一种模拟方式，输入问题后查看回答、证据依据和不确定性说明。</p>
          </div>
          <span className={simulationReady ? 'badge badge-success' : 'badge badge-muted'}>
            {simulationReady ? '可进入模拟实验台' : '尚未准备'}
          </span>
        </div>

        {!simulationReady ? (
          <div className="runtime-empty-state subtle-panel">
            <span className="badge badge-muted">waiting</span>
            <h4>请先点击重新分析，系统会自动准备模拟实验台。</h4>
            <p>完成后可运行思维模拟、互动模拟，或对比模拟。</p>
          </div>
        ) : (
          <div className="runtime-lab-grid simplified">
            <div className="runtime-console subtle-panel">
              <div className="runtime-control-block">
                <label>模式</label>
                <div className="runtime-engine-selector simple">
                  {[
                    { value: 'nuwa' as const, label: '思维模拟', ready: nuwaRunnable },
                    { value: 'colleague' as const, label: '互动模拟', ready: colleagueRunnable },
                    { value: 'compare' as const, label: '对比模拟', ready: Boolean(nuwaRunnable && colleagueRunnable) },
                  ].map(item => (
                    <button
                      key={item.value}
                      className={runtimeLabSkillType === item.value ? 'active' : ''}
                      disabled={!item.ready}
                      onClick={() => {
                        setRuntimeLabSkillType(item.value)
                        setRuntimeLabMode(item.value === 'nuwa' ? 'nuwa_thinking' : item.value === 'colleague' ? 'colleague_interaction' : 'compare')
                      }}
                    >
                      <strong>{item.label}</strong>
                    </button>
                  ))}
                </div>
              </div>

              <div className="form-group runtime-prompt-group">
                <label>输入问题</label>
                <textarea
                  ref={runtimePromptRef}
                  className="runtime-prompt"
                  value={runtimePrompt}
                  onChange={e => setRuntimePrompt(e.target.value)}
                  placeholder="输入你想测试的问题..."
                />
              </div>

              <div className="runtime-example-chips" aria-label="示例问题">
                {[
                  '这个人遇到复杂选择时会怎么判断？',
                  '这个人的沟通风格是什么？',
                  '如果资料不足，你会如何回答？',
                  '两个模拟视角对同一问题有什么不同？',
                ].map(prompt => (
                  <button key={prompt} type="button" onClick={() => handleRuntimeExamplePrompt(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>

              <div className="runtime-console-actions">
                <button
                  className="btn-primary"
                  onClick={handleRunWebsiteRuntime}
                  disabled={websiteRuntimeRunning || !runtimePrompt.trim() || !canRunWebsiteRuntime}
                >
                  {websiteRuntimeRunning ? <><span className="spinner" /> 运行中</> : '运行模拟'}
                </button>
                <button className="btn-secondary" onClick={handleClearWebsiteRuntime}>清空</button>
              </div>
              {!canRunWebsiteRuntime && (
                <p className="runtime-help-text">
                  {runtimeLabSkillType === 'compare'
                    ? '需要同时准备思维模拟和互动模拟才能对比。'
                    : '请先点击重新分析，系统会自动准备模拟实验台。'}
                </p>
              )}
            </div>

            <div className="runtime-output">
              {websiteRuntimeRunning ? (
                <RuntimeOutputSkeleton />
              ) : compareRuntimeResult ? (
                <CompareRuntimeView result={compareRuntimeResult} onCopy={handleCopyWebsiteAnswer} copied={copied} />
              ) : websiteRuntimeResult ? (
                <RuntimeResultView
                  result={websiteRuntimeResult}
                  showTrace={adminView}
                  traceOpen={runtimeTraceOpen}
                  copied={copied}
                  feedbackRating={feedbackRating}
                  feedbackNote={feedbackNote}
                  feedbackExpanded={feedbackExpanded}
                  feedbackBusy={feedbackBusy}
                  onToggleTrace={() => setRuntimeTraceOpen(v => !v)}
                  onCopy={() => handleCopyWebsiteAnswer(websiteRuntimeResult)}
                  onFeedbackRating={value => {
                    setFeedbackRating(value)
                    setFeedbackExpanded(value !== 'good')
                  }}
                  onFeedbackNote={value => setFeedbackNote(value)}
                  onFeedbackExpanded={setFeedbackExpanded}
                  onSubmitFeedback={handleSubmitWebsiteFeedback}
                />
              ) : (
                <div className="runtime-placeholder subtle-panel">
                  <span className="badge badge-muted">等待运行</span>
                  <h4>输入问题后运行模拟</h4>
                  <p>结果会包含回答、证据依据、不确定性和安全边界；技术细节默认隐藏。</p>
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      {/* ── Upload Card ── */}
      <div id="documents" className="card page-section-anchor page-documents-section" style={{ marginBottom: '1.5rem' }}>
        <div className="section-title" style={{ marginTop: 0 }}>
          <div>
            <h2>资料管理</h2>
            <p>上传文件，或直接粘贴文本内容作为分析资料。</p>
          </div>
        </div>

        {/* MinerU Status Banner */}
        {mineruStatus && (
          <div className={`subtle-panel mineru-status-banner ${mineruStatus.installed && mineruStatus.enabled ? 'mineru-ready' : 'mineru-missing'}`}>
            {mineruStatus.installed && mineruStatus.enabled ? (
              <div>
                <span className="badge badge-success">复杂文档解析已启用</span>
                <span style={{ marginLeft: '0.75rem', fontSize: '0.8rem', color: 'var(--muted)' }}>
                  复杂文档会自动解析为可分析文本。
                </span>
                {adminView && (
                  <div className="admin-diagnostics-inline">
                    backend={mineruStatus.backend} · method={mineruStatus.method} · lang={mineruStatus.lang}
                    {mineruStatus.image_analysis && ' · 图片分析: 开'}
                    {mineruStatus.backend === 'hybrid-auto-engine' && ' · hybrid 后端解析大型文档可能需要数分钟'}
                  </div>
                )}
              </div>
            ) : (
              <span>复杂文档解析未启用，仅支持 txt / md / json / csv</span>
            )}
          </div>
        )}

        <div className="document-input-shell">
          <div className="document-mode-tabs" role="tablist" aria-label="资料输入模式">
            <button
              type="button"
              role="tab"
              aria-selected={documentInputMode === 'upload'}
              className={documentInputMode === 'upload' ? 'active' : ''}
              onClick={() => setDocumentInputMode('upload')}
            >
              上传文件
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={documentInputMode === 'paste'}
              className={documentInputMode === 'paste' ? 'active' : ''}
              onClick={() => setDocumentInputMode('paste')}
            >
              粘贴文本
            </button>
          </div>

          <div className={`document-mode-panel ${documentInputMode === 'paste' ? 'is-paste' : 'is-upload'}`}>
            {documentInputMode === 'upload' ? (
              <div
                className={`upload-zone compact ${uploading ? 'dragover' : ''}`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('dragover') }}
                onDragLeave={e => e.currentTarget.classList.remove('dragover')}
                onDrop={e => {
                  e.preventDefault()
                  e.currentTarget.classList.remove('dragover')
                  handleUpload(e.dataTransfer.files)
                }}
              >
                {uploading ? (
                  <p>
                    <span className="spinner" />
                    {isMineruFile(uploadingFileName)
                      ? ' 正在调用 MinerU 解析，可能需要较长时间...'
                      : ' 上传处理中...'}
                  </p>
                ) : (
                  <p>拖拽文件到此处，或点击选择文件<br />
                    <span style={{ fontSize: '0.8rem', color: 'var(--c-text-muted)' }}>
                      支持 txt / md / json / csv / pdf / docx / pptx / xlsx / png / jpg / webp
                    </span>
                  </p>
                )}
              </div>
            ) : (
              <div className={`paste-composer ${pasteHighlighted ? 'highlight' : ''}`}>
                <div className="paste-composer-head">
                  <div>
                    <h3>快速录入</h3>
                    <p>直接粘贴聊天记录、文章、客户沟通内容或其他文本资料。</p>
                  </div>
                  <span className={`badge paste-meter-badge ${pasteMeter.level}`}>{pasteMeter.label}</span>
                </div>

                <label className="paste-field">
                  <span>标题 / 文件名</span>
                  <input
                    value={pasteTitle}
                    onChange={e => setPasteTitle(e.target.value)}
                    placeholder="微信聊天记录片段 / 客户沟通记录 / 文章内容"
                    disabled={pasteSaving}
                  />
                </label>

                <label className="paste-field">
                  <span>文本内容</span>
                  <textarea
                    ref={pasteTextRef}
                    value={pasteText}
                    onChange={e => {
                      setPasteText(e.target.value)
                      if (pasteNotice) setPasteNotice('')
                    }}
                    onKeyDown={handlePastedTextKeyDown}
                    placeholder="直接粘贴聊天记录、文章、客户沟通内容或其他文本资料..."
                    disabled={pasteSaving}
                  />
                </label>

                <div className="paste-meter-card">
                  <div className="paste-meter-stats">
                    <span><strong>{pastedCharCount.toLocaleString()}</strong> 字</span>
                    <span><strong>{pastedChunkEstimate}</strong> chunks</span>
                    <span>{pasteMeter.hint}</span>
                  </div>
                  <div className="paste-mini-track" aria-hidden="true">
                    <div className={`paste-mini-fill ${pasteMeter.level}`} style={{ width: `${pasteMeter.percent}%` }} />
                  </div>
                </div>

                {pasteNotice && <p className="paste-notice">{pasteNotice}</p>}

                <div className="paste-actions">
                  <button type="button" className="btn-secondary" onClick={handleReadClipboard} disabled={pasteSaving}>
                    从剪贴板读取
                  </button>
                  <button type="button" className="btn-secondary" onClick={handleClearPastedText} disabled={pasteSaving || (!pasteText && !pasteTitle)}>
                    清空
                  </button>
                  <button type="button" className="btn-primary" onClick={handleSavePastedText} disabled={!canSavePastedText}>
                    {pasteSaving ? <><span className="spinner" /> 保存中</> : '保存为资料'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.markdown,.json,.csv,.pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg,.webp"
          style={{ display: 'none' }}
          onChange={e => handleUpload(e.target.files)}
        />

        {sufficiency && (
          <div className="sufficiency-bar">
            <div className="sufficiency-head">
              <span>资料充分度 · {sufficiency.label}</span>
              <span>{sufficiency.total_chars.toLocaleString()} 字 · {sufficiency.chunk_count} chunks</span>
            </div>
            <div className="bar-track">
              <div className={`bar-fill ${sufficiency.level}`} />
            </div>
          </div>
        )}
        {sufficiency && (
          <p style={{ fontSize: '0.8rem', color: 'var(--c-text-muted)', marginBottom: '0.5rem' }}>
            {sufficiency.description}
          </p>
        )}

        {documents.length > 0 ? (
          <div className="file-list">
            <h3 style={{ fontSize: '0.92rem', marginBottom: '0.2rem' }}>已上传资料 ({documents.length} 个文件)</h3>
            {documents.map(doc => (
              <div key={doc.id} className="file-item">
                <div className="file-main">
                  <div>
                    <div className="file-name">{doc.filename}</div>
                    <div className="file-meta">
                      <span className={doc.parser === 'mineru' ? 'badge badge-info' : 'badge badge-muted'}>
                        parser · {doc.parser || 'builtin'}
                      </span>
                      <span>{doc.file_type}</span>
                      <span>{doc.char_count.toLocaleString()} 字符</span>
                      <span>{doc.chunk_count} 片段</span>
                      <span>{new Date(doc.uploaded_at).toLocaleDateString('zh-CN')}</span>
                    </div>
                  </div>
                  {doc.parse_status === 'failed' && (
                    <span className="badge badge-danger">解析失败</span>
                  )}
                  <div className="file-actions">
                    <button
                      className="btn-sm"
                      onClick={() => handlePreviewDocument(doc.id)}
                      disabled={previewLoading}
                    >
                      预览
                    </button>
                    <details className="file-more-actions">
                      <summary>更多</summary>
                      <button
                        className="btn-sm"
                        onClick={() => setDeletingId(doc.id)}
                      >
                        删除资料
                      </button>
                    </details>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state" style={{ padding: '1rem' }}>
            <p style={{ fontSize: '0.85rem' }}>还没有上传任何资料</p>
          </div>
        )}
      </div>

      {/* ── Deep Portrait Dashboard ── */}
      <section id="portrait" className="page-section-anchor page-portrait-section">
        {profile.has_analysis && portraitSections.length > 0 ? (
          <>
            <div className="section-title">
              <div>
                <h2>证据化画像</h2>
                <p>模块默认以列表展示，点击后在抽屉中查看完整判断和证据。</p>
              </div>
              <div className="portrait-actions">
                <span className="badge badge-info">{portraitSections.length} modules</span>
              </div>
            </div>
            <div className="portrait-filter-row" role="tablist" aria-label="画像过滤">
              {[
                ['all', '全部'],
                ['evidence', '有证据'],
                ['insufficient', '资料不足'],
                ['high', '高置信度'],
                ['low', '低置信度'],
              ].map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={portraitFilter === value ? 'active' : ''}
                  onClick={() => setPortraitFilter(value as PortraitFilter)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="portrait-compact-list">
              {filteredPortraitItems.map(item => {
                return (
                  <article key={item.section.anchor} id={item.section.anchor} className={`compact-card portrait-list-item ${item.evidence && !item.evidence.data_sufficient ? 'insufficient' : ''}`}>
                    <div className="portrait-list-main">
                      <div>
                        <div className="module-index">Module {item.moduleNo || '--'}</div>
                        <h3>{item.title}</h3>
                        <p>{item.summary}</p>
                        <div className="status-row">
                          {item.evidence ? (
                            <>
                              <span className={item.evidence.data_sufficient ? 'badge badge-success' : 'badge badge-warning'}>
                                {item.evidence.data_sufficient ? '有证据' : '资料不足'}
                              </span>
                              <span className="badge badge-muted">{item.claimCount} 条判断</span>
                              {item.avgClaimConfidence !== null && <span className="badge badge-info">置信度 {item.avgClaimConfidence}/100</span>}
                            </>
                          ) : (
                            <span className="badge badge-muted">建议重新分析生成证据链</span>
                          )}
                        </div>
                      </div>
                      <button
                        className="btn-sm"
                        type="button"
                        onClick={() => setPortraitDrawer({
                          title: item.title,
                          content: item.section.content,
                          moduleNo: item.moduleNo,
                          evidence: item.evidence,
                        })}
                      >
                        查看详情
                      </button>
                    </div>
                  </article>
                )
              })}
              {filteredPortraitItems.length === 0 && (
                <div className="empty-state compact-empty">
                  <p>当前筛选下没有画像模块。</p>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <div className="empty-state">
              <h3>尚未生成分析报告</h3>
              <p>请先上传资料，然后点击上方“开始分析”生成证据化人物画像。</p>
            </div>
          </div>
        )}
      </section>

      {/* ── Style Card ── */}
      {profile.has_analysis && profile.latest_style_card && (
        <details className="card style-card-display page-style-section compact-style-card">
          <summary>
            <div>
              <strong>风格卡附录</strong>
              <span>结构化表达风格说明，默认折叠；需要复制或审阅时再展开。</span>
            </div>
            <em>画像附录</em>
          </summary>
          <div className="style-card-body">
            <div className="section-title" style={{ marginTop: 0 }}>
              <div>
                <h2>AI 风格卡</h2>
                <p>用于后续导出和高级工具读取；普通画像结论以上方 14 个模块为主。</p>
              </div>
              <button className="copy-btn" onClick={handleCopyStyleCard}>
                {copied === 'style-card' ? '已复制 ✓' : '复制风格卡'}
              </button>
            </div>
            {styleSections.length > 0 ? (
              <div className="dashboard-grid">
                {styleSections.map(s => (
                  <div key={s.anchor} className="dashboard-card">
                    <h3>{s.title}</h3>
                    <p className="portrait-module-summary">{summarizeMarkdown(s.content)}</p>
                    <details className="portrait-module-details">
                      <summary>展开详情</summary>
                      <div className="card-body">
                        <ReactMarkdown>{s.content}</ReactMarkdown>
                      </div>
                    </details>
                  </div>
                ))}
              </div>
            ) : (
              <ExpandableMarkdown content={profile.latest_style_card} maxChars={900} />
            )}
          </div>
        </details>
      )}

      {/* ── Export ── */}
      <div id="exports" className="card page-section-anchor page-export-section" style={{ marginTop: '1rem' }}>
        <div className="section-title" style={{ marginTop: 0 }}>
          <div>
            <h2>导出与维护</h2>
            <p>优先导出完整分析报告；数据集和能力文件适合后续高级使用。</p>
          </div>
        </div>
        <div className="action-grid export-primary-grid">
          <ExportAction title="完整分析报告" desc="导出包含画像、证据链和风格卡的 Markdown 报告。">
            <button className="btn-primary" onClick={handleExportAnalysisReport} disabled={!profile.has_analysis || exporting === 'analysis-report'}>
              {exporting === 'analysis-report' ? <><span className="spinner" /> 导出中</> : '导出报告'}
            </button>
          </ExportAction>
        </div>
        <details className="advanced-export-details">
          <summary>
            <strong>高级导出与维护</strong>
            <span>风格卡、RAG Dataset、SFT Dataset 和文本片段维护。</span>
          </summary>
          <div className="action-grid">
            <ExportAction title="风格卡" desc="导出结构化风格卡，用于后续提示词或模拟配置。">
              <button className="btn-secondary" onClick={handleExportSkillCard} disabled={!profile.has_analysis || exporting === 'skill-card'}>
                {exporting === 'skill-card' ? <><span className="spinner" /> 导出中</> : '导出'}
              </button>
            </ExportAction>
            <ExportAction title="RAG Dataset" desc="Easy Dataset 兼容 JSONL，包含片段和证据 metadata。">
              <button className="btn-secondary" onClick={handleExportRAGDataset} disabled={profile.chunk_count === 0 || exporting === 'rag'}>
                {exporting === 'rag' ? <><span className="spinner" /> 导出中</> : '导出'}
              </button>
            </ExportAction>
            <ExportAction title="SFT Dataset" desc="生成训练样本 JSONL，便于后续高级数据整理。">
              <button className="btn-secondary" onClick={handleExportSFT} disabled={profile.chunk_count === 0 || exporting === 'sft'}>
                {exporting === 'sft' ? <><span className="spinner" /> 导出中</> : '导出'}
              </button>
            </ExportAction>
            <ExportAction title="文本片段维护" desc="重新从已有文档构建 chunks，不删除原始文件。">
              <button className="btn-secondary" onClick={handleRebuildChunks} disabled={rebuilding || profile.chunk_count === 0}>
                {rebuilding ? <><span className="spinner" /> 重建中</> : '重建文本片段'}
              </button>
            </ExportAction>
          </div>
          <p className="export-note">RAG Dataset = 检索数据 JSONL · SFT Dataset = 训练样本 JSONL。</p>
        </details>
        {!profile.has_analysis && (
          <p style={{ fontSize: '0.8rem', color: 'var(--c-text-muted)', marginTop: '0.5rem' }}>
            风格卡需要先生成画像报告
          </p>
        )}
      </div>
      </div>
      </div>

      {portraitDrawer && (
        <div className="drawer-backdrop" onClick={() => setPortraitDrawer(null)}>
          <aside className="drawer-panel bottom-sheet" onClick={e => e.stopPropagation()} aria-label="画像模块详情">
            <div className="drawer-header">
              <div>
                <span className="badge badge-info">Module {portraitDrawer.moduleNo || '--'}</span>
                <h3>{portraitDrawer.title}</h3>
              </div>
              <button className="modal-close" onClick={() => setPortraitDrawer(null)} aria-label="关闭">×</button>
            </div>
            <div className="drawer-body">
              <div className="portrait-drawer-summary">
                {portraitDrawer.evidence ? (
                  <div className="status-row">
                    <span className={portraitDrawer.evidence.data_sufficient ? 'badge badge-success' : 'badge badge-warning'}>
                      {portraitDrawer.evidence.data_sufficient ? '有证据' : '资料不足'}
                    </span>
                    <span className="badge badge-muted">{portraitDrawer.evidence.claims.length} 条判断</span>
                  </div>
                ) : (
                  <p className="legacy-module-note">该模块来自旧版报告，建议重新分析以生成证据链。</p>
                )}
              </div>
              <div className="drawer-markdown">
                <ReactMarkdown>{portraitDrawer.content}</ReactMarkdown>
              </div>
              {portraitDrawer.evidence && (
                <div className="drawer-evidence-list">
                  <h4>证据摘要</h4>
                  {portraitDrawer.evidence.claims.slice(0, 6).map((claim, index) => (
                    <div className="evidence-claim compact-evidence-claim" key={`${claim.claim}-${index}`}>
                      <strong>{claim.claim}</strong>
                      <div className="evidence-meta">
                        <span className="badge badge-info">置信度 {claim.confidence_score}/100</span>
                        <span className="badge badge-muted">{claim.evidence.length} quotes</span>
                      </div>
                      {claim.evidence[0]?.quote && (
                        <blockquote className="quote-block">
                          {claim.evidence[0].quote.length > 220 ? `${claim.evidence[0].quote.slice(0, 220)}...` : claim.evidence[0].quote}
                        </blockquote>
                      )}
                    </div>
                  ))}
                  <button
                    className="btn-secondary"
                    onClick={() => {
                      setEvidenceModal({ moduleName: `${portraitDrawer.moduleNo}. ${portraitDrawer.title}`, moduleIndex: portraitDrawer.moduleNo })
                    }}
                  >
                    查看完整证据
                  </button>
                </div>
              )}
            </div>
          </aside>
        </div>
      )}

      {/* ── Preview Modal ── */}
      {previewDoc && (
        <div className="drawer-backdrop" onClick={() => setPreviewDoc(null)}>
          <aside className="drawer-panel bottom-sheet file-preview-drawer" onClick={e => e.stopPropagation()} aria-label="资料预览">
            <div className="drawer-header">
              <div>
                <h3 style={{ margin: 0, fontSize: '1rem' }}>资料预览</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}>{previewDoc.filename}</p>
              </div>
              <button className="modal-close" onClick={() => setPreviewDoc(null)} aria-label="关闭">×</button>
            </div>
            <div className="drawer-body">
              <div className="status-row" style={{ marginBottom: '0.75rem' }}>
                <span className="badge badge-muted">解析 · {previewDoc.parser || 'builtin'}</span>
                <span className="badge badge-muted">状态 · {previewDoc.parse_status || '正常'}</span>
                <span className="badge badge-muted">{previewDoc.char_count.toLocaleString()} 字符</span>
              </div>
              <pre className="preview-pre">
                {previewDoc.preview_text}
              </pre>
              {previewDoc.preview_text.length >= 3000 && (
                <p style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.5rem' }}>
                  仅显示前 3000 字。完整内容请查看原始文件。
                </p>
              )}
            </div>
          </aside>
        </div>
      )}

      {/* ── Skill Spec Modal ── */}
      {skillSpec && (
        <div className="modal-overlay" onClick={() => setSkillSpec(null)}>
          <div className="modal-content skill-spec-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 style={{ margin: 0, fontSize: '1rem' }}>{skillSpec.project_name}</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}>
                  {skillSpec.source_repo}
                </p>
              </div>
              <button className="modal-close" onClick={() => setSkillSpec(null)} aria-label="关闭">×</button>
            </div>
            <p style={{ color: 'var(--muted-strong)', fontSize: '0.86rem', marginBottom: '0.85rem' }}>
              {skillSpec.description}
            </p>
            <div className="skill-spec-grid">
              <SpecList title="用途" items={skillSpec.skill_purpose} />
              <SpecList title="输入要求" items={skillSpec.input_requirements} />
              <SpecList title="工作流" items={skillSpec.workflow} />
              <SpecList title="输出契约" items={skillSpec.output_contract} />
              <SpecList title="宿主" items={skillSpec.runtime_hosts} />
              <SpecList title="局限" items={skillSpec.limitations} />
            </div>
            <div className="subtle-panel" style={{ marginTop: '0.85rem' }}>
              <strong>已读取文件</strong>
              <div className="generated-file-list" style={{ marginTop: '0.5rem' }}>
                {skillSpec.raw_files_read.map(file => <span key={file}>{file}</span>)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── Dry Run Modal ── */}
      {dryRunResult && (
        <div className="modal-overlay" onClick={() => setDryRunResult(null)}>
          <div className="modal-content skill-spec-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 style={{ margin: 0, fontSize: '1rem' }}>Dry-run 模拟运行</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}>
                  runtime_simulated={String(dryRunResult.runtime_simulated)} · actual_runtime_invoked={String(dryRunResult.actual_runtime_invoked)}
                </p>
              </div>
              <button className="modal-close" onClick={() => setDryRunResult(null)} aria-label="关闭">×</button>
            </div>
            <div className="status-row" style={{ marginBottom: '0.75rem' }}>
              <span className="badge badge-info">level · {dryRunResult.level}</span>
              <span className="badge badge-muted">score · {dryRunResult.validation_score}</span>
              {dryRunResult.used_files.map(file => <span className="badge badge-muted" key={file}>{file}</span>)}
            </div>
            {dryRunResult.warnings.length > 0 && (
              <div className="warning-panel">
                <strong>Warnings</strong>
                <ul>{dryRunResult.warnings.map(w => <li key={w}>{w}</li>)}</ul>
              </div>
            )}
            <pre className="preview-pre">{dryRunResult.simulated_output || dryRunResult.error || '无输出'}</pre>
          </div>
        </div>
      )}

      {/* ── Runtime Test Cases Modal ── */}
      {runtimeCases && (
        <div className="modal-overlay" onClick={() => setRuntimeCases(null)}>
          <div className="modal-content skill-spec-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 style={{ margin: 0, fontSize: '1rem' }}>Runtime 测试用例</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}>
                  target={runtimeCases.runtime_target} · 系统只生成用例，不自动访问外部 runtime
                </p>
              </div>
              <button className="modal-close" onClick={() => setRuntimeCases(null)} aria-label="关闭">×</button>
            </div>
            <div className="status-row" style={{ marginBottom: '0.75rem' }}>
              <span className="badge badge-info">cases · {runtimeCases.test_cases.length}</span>
              {runtimeCases.markdown_path && <span className="badge badge-muted">runtime_test_cases.md</span>}
              {runtimeCases.json_path && <span className="badge badge-muted">runtime_test_cases.json</span>}
            </div>
            <div className="runtime-case-list">
              {runtimeCases.test_cases.map(item => (
                <div className="runtime-case" key={item.case_id}>
                  <div className="runtime-case-head">
                    <span className="badge badge-muted">{item.case_id}</span>
                    <strong>{item.title}</strong>
                  </div>
                  <p><strong>Prompt</strong></p>
                  <pre>{item.prompt}</pre>
                  <p><strong>Expected</strong> {item.expected_behavior}</p>
                  <div className="generated-file-list">
                    {item.pass_criteria.map(c => <span key={c}>{c}</span>)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── External Runtime Result Modal ── */}
      {runtimeModalSkill && (
        <div className="modal-overlay" onClick={() => setRuntimeModalSkill(null)}>
          <div className="modal-content skill-spec-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 style={{ margin: 0, fontSize: '1rem' }}>回填外部运行结果</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}>
                  L5c 需要外部 runtime 实测结果；系统不会自动访问 Codex / Claude Code / Hermes。
                </p>
              </div>
              <button className="modal-close" onClick={() => setRuntimeModalSkill(null)} aria-label="关闭">×</button>
            </div>
            <div className="warning-panel">
              Dry-run 是站内模拟，不等于真实 runtime。请先把 ZIP 安装到外部 runtime，按 runtime_test_cases.md 逐条运行，再把完整输出粘贴回来。
            </div>
            <div className="runtime-form-grid">
              <div className="form-group">
                <label>Runtime target</label>
                <select
                  value={runtimeForm.runtime_target}
                  onChange={e => setRuntimeForm({ ...runtimeForm, runtime_target: e.target.value })}
                >
                  <option value="codex">Codex</option>
                  <option value="claude_code">Claude Code</option>
                  <option value="hermes">Hermes</option>
                  <option value="generic_agent_skill">Generic</option>
                </select>
              </div>
              <div className="form-group">
                <label>Evidence of runtime</label>
                <input
                  value={runtimeForm.evidence_of_runtime}
                  onChange={e => setRuntimeForm({ ...runtimeForm, evidence_of_runtime: e.target.value })}
                  placeholder="例如运行时间、宿主版本、截图说明或日志位置"
                />
              </div>
            </div>
            <div className="form-group">
              <label>Tester note</label>
              <textarea
                rows={3}
                value={runtimeForm.tester_note}
                onChange={e => setRuntimeForm({ ...runtimeForm, tester_note: e.target.value })}
                placeholder="说明你在哪个外部 runtime 中安装、如何触发 Skill。"
              />
            </div>
            <div className="form-group">
              <label>外部运行输出</label>
              <textarea
                rows={10}
                value={runtimeForm.test_output_text}
                onChange={e => setRuntimeForm({ ...runtimeForm, test_output_text: e.target.value })}
                placeholder="建议按 case_id 粘贴：activation / evidence_policy / uncertainty / safety_boundary / style_consistency ..."
              />
            </div>
            <div className="form-actions">
              <button className="btn-secondary" onClick={() => handleSubmitRuntimeResult(false)} disabled={runtimeBusySkill === runtimeModalSkill.id || !runtimeForm.test_output_text.trim()}>
                只提交回填
              </button>
              <button className="btn-primary" onClick={() => handleSubmitRuntimeResult(true)} disabled={runtimeBusySkill === runtimeModalSkill.id || !runtimeForm.test_output_text.trim()}>
                {runtimeBusySkill === runtimeModalSkill.id ? <><span className="spinner" /> 评估中</> : '评估运行结果'}
              </button>
            </div>
            {runtimeEvaluation && (
              <div className={`runtime-eval-panel ${runtimeEvaluation.can_mark_l5c ? 'passed' : 'failed'}`}>
                <div className="status-row">
                  <span className={runtimeEvaluation.can_mark_l5c ? 'badge badge-success' : 'badge badge-warning'}>
                    score · {runtimeEvaluation.score}
                  </span>
                  <span className={runtimeEvaluation.can_mark_l5c ? 'badge badge-success' : 'badge badge-muted'}>
                    {runtimeEvaluation.can_mark_l5c ? '达到 L5c' : '未达到 L5c'}
                  </span>
                  <span className="badge badge-muted">judgeable · {runtimeEvaluation.judgeable_cases}</span>
                  <span className={runtimeEvaluation.safety_boundary_passed ? 'badge badge-success' : 'badge badge-danger'}>safety</span>
                  <span className={runtimeEvaluation.evidence_policy_passed ? 'badge badge-success' : 'badge badge-danger'}>evidence</span>
                </div>
                {runtimeEvaluation.failed_cases.length > 0 && (
                  <p><strong>Failed cases:</strong> {runtimeEvaluation.failed_cases.join(', ')}</p>
                )}
                {runtimeEvaluation.warnings.length > 0 && (
                  <ul>{runtimeEvaluation.warnings.map(w => <li key={w}>{w}</li>)}</ul>
                )}
                <p><strong>Recommended fix:</strong> {runtimeEvaluation.recommended_fix}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Evidence Modal ── */}
      {evidenceModal && (() => {
        const evidence = evidenceMap[evidenceModal.moduleIndex]
        return (
        <div className="modal-overlay" onClick={() => setEvidenceModal(null)}>
          <div className="evidence-modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3 style={{ margin: 0, fontSize: '1rem' }}>证据链</h3>
                <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}>
                  {evidenceModal.moduleName}
                </p>
              </div>
              <button className="modal-close" onClick={() => setEvidenceModal(null)} aria-label="关闭">×</button>
            </div>

            {!evidence ? (
              <div className="empty-state" style={{ padding: '2rem 1rem' }}>
                <p>旧分析未生成证据，请重新分析以生成 evidence_map。</p>
              </div>
            ) : !evidence.data_sufficient ? (
              <div className="warning-panel">
                <strong>资料不足</strong>
                <p style={{ marginTop: '0.5rem' }}>此模块资料不足，无法提供可靠证据。建议上传更多相关资料后重新分析。</p>
              </div>
            ) : (
              <div>
                {evidence.claims.map((claim: EvidenceClaim, ci: number) => (
                  <div key={ci} className="evidence-claim">
                    <div style={{ fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.9rem' }}>
                      判断 {ci + 1}：{claim.claim}
                    </div>

                    <div className="evidence-meta">
                      <span className={claim.confidence_score >= 70 ? 'badge badge-success' : claim.confidence_score >= 40 ? 'badge badge-warning' : 'badge badge-danger'}>
                        置信度 {claim.confidence_score}/100
                      </span>
                      {claim.contradiction && <span className="badge badge-danger">矛盾：{claim.contradiction}</span>}
                    </div>

                    {claim.evidence.length > 0 && (
                      <div style={{ marginBottom: '0.5rem' }}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600, marginBottom: '0.3rem', color: 'var(--c-text-muted)' }}>证据摘录：</div>
                        {claim.evidence.map((ev, ei: number) => (
                          <div key={ei} className={`quote-block ${ev.similarity_score && ev.similarity_score >= 0.7 ? 'high-similarity' : ''}`}>
                            <div className="evidence-meta" style={{ marginTop: 0 }}>
                              <span className="badge badge-muted">chunk_id {ev.chunk_id ?? ev.chunk_index}</span>
                              {ev.filename && <span className="badge badge-muted">{ev.filename}</span>}
                              <span className={ev.retrieval_method === 'vector' ? 'badge badge-info' : 'badge badge-muted'}>
                                {ev.retrieval_method === 'vector' ? 'vector' : 'keyword'}
                              </span>
                              {ev.similarity_score != null && (
                                <span className={ev.similarity_score >= 0.7 ? 'badge badge-success' : 'badge badge-muted'}>
                                  similarity {Number(ev.similarity_score).toFixed(4)}
                                </span>
                              )}
                            </div>
                            <p style={{ marginTop: '0.35rem' }}>{ev.quote}</p>
                          </div>
                        ))}
                      </div>
                    )}

                    {claim.data_gap && (
                      <div style={{ fontSize: '0.8rem', color: 'var(--c-warning)' }}>
                        资料不足项：{claim.data_gap}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div style={{ marginTop: '1rem', textAlign: 'right' }}>
              <button className="btn-secondary" onClick={() => setEvidenceModal(null)}>关闭</button>
            </div>
          </div>
        </div>
        )
      })()}

      {/* ── Delete Confirmation Modal ── */}
      {deletingId && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: 420, textAlign: 'center' }}>
            <h3 style={{ marginTop: 0 }}>确认删除</h3>
            <p style={{ color: 'var(--muted)', fontSize: '0.88rem', marginTop: '0.5rem' }}>
              删除后将移除该文档记录及其所有文本片段。原始上传文件保留在磁盘上。
            </p>
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', marginTop: '1rem' }}>
              <button
                className="btn-danger"
                onClick={() => handleDeleteDocument(deletingId)}
                disabled={deleting}
              >
                {deleting ? '删除中...' : '确认删除'}
              </button>
              <button className="btn-secondary" onClick={() => setDeletingId(null)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Quality Metric mini-component ──
function QualityMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  )
}

function PageMiniNav({
  items,
  activeSection,
  onSelect,
}: {
  items: { id: string; label: string; hint?: string }[];
  activeSection: string;
  onSelect: (id: string) => void;
}) {
  return (
    <nav className="profile-mini-nav workbench-sidebar workbench-tabs" aria-label="页面导航">
      {items.map(item => (
        <button
          type="button"
          key={item.id}
          className={activeSection === item.id ? 'active' : ''}
          onClick={() => onSelect(item.id)}
        >
          <strong>{item.label}</strong>
          {item.hint && <span>{item.hint}</span>}
        </button>
      ))}
    </nav>
  )
}

function PipelinePanel({
  hasAnalysis,
  chunkCount,
  analyzing,
  steps,
  result,
  simulationReady,
  onRun,
}: {
  hasAnalysis: boolean;
  chunkCount: number;
  analyzing: boolean;
  steps: Record<PipelineStepKey, PipelineUiStatus>;
  result: ProfilePipelineResult | null;
  simulationReady: boolean;
  onRun: () => void;
}) {
  const statusLabel: Record<string, string> = {
    pending: '等待',
    running: '进行中',
    done: '完成',
    warning: '提示',
    failed: '失败',
  }
  if (!analyzing && result) {
    const needUpload = result.pipeline_status === 'need_upload' || chunkCount === 0
    const hasErrors = result.errors.length > 0
    const compactTone = needUpload || result.warnings.length > 0
      ? 'badge badge-warning'
      : hasErrors
        ? 'badge badge-danger'
        : simulationReady
          ? 'badge badge-success'
          : 'badge badge-info'
    const compactTitle = needUpload
      ? '请先上传资料'
      : hasErrors
        ? '分析流程存在错误'
        : simulationReady
          ? '模拟实验台已准备'
          : '画像已完成，部分模拟准备存在提示'
    const compactDesc = needUpload
      ? '上传授权资料后即可开始分析，后续会自动生成画像并准备模拟实验台。'
      : result.warnings[0] || result.next_actions[0] || '分析流程已收尾。'
    return (
      <section className="card pipeline-panel pipeline-panel-compact page-pipeline-section">
        <div className="pipeline-compact-head">
          <div>
            <span className={compactTone}>{needUpload ? '需要资料' : hasErrors ? '需要检查' : '流程完成'}</span>
            <h2>{compactTitle}</h2>
            <p>{compactDesc}</p>
          </div>
          <button className="btn-secondary" onClick={onRun} disabled={chunkCount === 0}>
            {hasAnalysis ? '重新分析' : '开始分析'}
          </button>
        </div>
        <details className="pipeline-compact-details">
          <summary>查看流程步骤</summary>
          <div className="pipeline-stepper compact">
            {PIPELINE_STEPS.map(item => {
              const status = steps[item.key] || 'pending'
              return (
                <div className={`pipeline-step ${status}`} key={item.key}>
                  <span>{statusLabel[status] || status}</span>
                  <strong>{item.title}</strong>
                  <p>{item.desc}</p>
                </div>
              )
            })}
          </div>
          {result.warnings.length > 0 && (
            <div className="pipeline-message warning">{result.warnings.slice(0, 3).join('；')}</div>
          )}
          {result.errors.length > 0 && (
            <div className="pipeline-message failed">{result.errors.join('；')}</div>
          )}
        </details>
      </section>
    )
  }
  return (
    <section className="card pipeline-panel page-pipeline-section">
      <div className="pipeline-panel-head">
        <div>
          <span className={simulationReady ? 'badge badge-success' : hasAnalysis ? 'badge badge-warning' : 'badge badge-muted'}>
            {simulationReady ? '模拟已准备' : hasAnalysis ? '分析已完成' : '待分析'}
          </span>
          <h2>{hasAnalysis ? '重新分析并准备模拟' : '开始分析'}</h2>
          <p>系统会自动完成资料解析、证据画像、模拟能力准备和站内模拟入口开放。</p>
        </div>
        <button className="btn-primary" onClick={onRun} disabled={analyzing || chunkCount === 0}>
          {analyzing ? <><span className="spinner" /> 准备中</> : hasAnalysis ? '重新分析' : '开始分析'}
        </button>
      </div>

      <div className="pipeline-stepper">
        {PIPELINE_STEPS.map(item => {
          const status = steps[item.key] || 'pending'
          return (
            <div className={`pipeline-step ${status}`} key={item.key}>
              <span>{statusLabel[status] || status}</span>
              <strong>{item.title}</strong>
              <p>{item.desc}</p>
            </div>
          )
        })}
      </div>

      {chunkCount === 0 && (
        <div className="pipeline-message warning">
          请先上传资料。上传后点击“开始分析”，系统会自动准备画像和模拟实验台。
        </div>
      )}
      {result && result.warnings.length > 0 && (
        <div className="pipeline-message warning">
          {result.warnings.slice(0, 2).join('；')}
          {result.warnings.length > 2 ? `；另有 ${result.warnings.length - 2} 条提示，可在高级技术详情查看。` : ''}
        </div>
      )}
      {result && result.errors.length > 0 && (
        <div className="pipeline-message failed">{result.errors.join('；')}</div>
      )}
      {result && result.next_actions.length > 0 && (
        <div className="pipeline-message">
          {result.next_actions[0]}
        </div>
      )}
    </section>
  )
}

function ExportAction({ title, desc, children }: { title: string; desc: string; children: ReactNode }) {
  return (
    <div className="action-card">
      <h3>{title}</h3>
      <p>{desc}</p>
      {children}
    </div>
  )
}

function SkillFoundryLayer({
  index,
  title,
  description,
  children,
}: {
  index: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="skill-foundry-layer">
      <div className="skill-layer-heading">
        <span>{index}</span>
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
      </div>
      {children}
    </section>
  )
}

function RuntimeProvenancePanel({
  activeEngine,
  sourceRepo,
  skillFilesLoaded,
  llmProvider,
  evidenceSource,
  externalRuntime,
}: {
  activeEngine: string;
  sourceRepo: string;
  skillFilesLoaded: string;
  llmProvider: string;
  evidenceSource: string;
  externalRuntime: string;
}) {
  return (
    <div className="runtime-provenance-panel">
      <div className="runtime-provenance-note">
        <span className="badge badge-info">Website-native runtime</span>
        <p>
          Website Runtime 会读取生成的 Skill 文件，并在站内调用当前 LLM provider 运行。
          它不等于 Codex / Claude / Hermes 外部 L5c。
        </p>
      </div>
      <div className="runtime-provenance-grid">
        <QualityMetric label="Active Engine" value={activeEngine} />
        <QualityMetric label="Source Repo" value={sourceRepo} />
        <QualityMetric label="Skill Files Loaded" value={skillFilesLoaded} />
        <QualityMetric label="LLM Provider" value={llmProvider} />
        <QualityMetric label="Evidence Source" value={evidenceSource} />
        <QualityMetric label="Runtime Type" value="Website-native runtime" />
        <QualityMetric label="External Runtime" value={externalRuntime} />
      </div>
    </div>
  )
}

function RuntimeOutputSkeleton() {
  return (
    <div className="runtime-result-card runtime-skeleton-card">
      <div className="runtime-result-head">
        <div>
          <span className="skeleton skeleton-badge" />
          <span className="skeleton skeleton-title" />
          <span className="skeleton skeleton-line short" />
        </div>
        <span className="skeleton skeleton-button" />
      </div>
      <div className="runtime-answer">
        <span className="skeleton skeleton-line" />
        <span className="skeleton skeleton-line" />
        <span className="skeleton skeleton-line medium" />
      </div>
      <div className="runtime-meta-grid">
        <span className="skeleton skeleton-panel" />
        <span className="skeleton skeleton-panel" />
      </div>
    </div>
  )
}

function ExpandableMarkdown({
  content,
  maxChars = 720,
  empty = '无输出',
}: {
  content?: string | null;
  maxChars?: number;
  empty?: string;
}) {
  const [expanded, setExpanded] = useState(false)
  const text = content?.trim() || empty
  const shouldCollapse = text.length > maxChars
  const visible = shouldCollapse && !expanded ? `${text.slice(0, maxChars)}...` : text
  return (
    <div className="expandable-markdown">
      <ReactMarkdown>{visible}</ReactMarkdown>
      {shouldCollapse && (
        <button className="btn-sm" type="button" onClick={() => setExpanded(v => !v)}>
          {expanded ? '收起' : '展开完整内容'}
        </button>
      )}
    </div>
  )
}

function RuntimeResultView({
  result,
  showTrace,
  traceOpen,
  copied,
  feedbackRating,
  feedbackNote,
  feedbackExpanded,
  feedbackBusy,
  onToggleTrace,
  onCopy,
  onFeedbackRating,
  onFeedbackNote,
  onFeedbackExpanded,
  onSubmitFeedback,
}: {
  result: SkillWebsiteRun;
  showTrace: boolean;
  traceOpen: boolean;
  copied: string;
  feedbackRating: SkillRuntimeFeedbackPayload['rating'];
  feedbackNote: string;
  feedbackExpanded: boolean;
  feedbackBusy: boolean;
  onToggleTrace: () => void;
  onCopy: () => void;
  onFeedbackRating: (value: SkillRuntimeFeedbackPayload['rating']) => void;
  onFeedbackNote: (value: string) => void;
  onFeedbackExpanded: (value: boolean) => void;
  onSubmitFeedback: () => void;
}) {
  const safety = result.safety_check || {}
  const feedbackOptions: { value: SkillRuntimeFeedbackPayload['rating']; label: string }[] = [
    { value: 'good', label: '准确' },
    { value: 'not_like_person', label: '不像这个人' },
    { value: 'missing_evidence', label: '缺少证据' },
    { value: 'unsafe', label: '不安全' },
    { value: 'inaccurate', label: '不准确' },
  ]
  const [activeResultTab, setActiveResultTab] = useState<'answer' | 'evidence' | 'uncertainty' | 'safety' | 'trace'>('answer')
  const resultTabs: { id: typeof activeResultTab; label: string }[] = [
    { id: 'answer', label: '回答' },
    { id: 'evidence', label: `证据 ${result.evidence_used.length}` },
    { id: 'uncertainty', label: '不确定性' },
    { id: 'safety', label: '安全' },
    ...(showTrace ? [{ id: 'trace' as const, label: '技术记录' }] : []),
  ]
  return (
    <div className="runtime-result-card slide-up">
      <div className="runtime-result-head">
        <div>
          <span className={runtimeStatusBadgeClass(result.status)}>{result.status}</span>
          <h4>{skillTypeLabel(result.skill_type as 'nuwa' | 'colleague' | 'compare')} · {runtimeModeLabel(result.runtime_mode)}</h4>
          <p>{result.model_provider || 'provider unavailable'} · {formatDateTime(result.created_at)}</p>
        </div>
        <button className="btn-sm" onClick={onCopy}>
          {copied === 'website-runtime-answer' ? '已复制' : '复制回答'}
        </button>
        {copied === 'website-runtime-answer' && <span className="runtime-copy-toast">已复制</span>}
      </div>

      {result.error && <div className="warning-panel">模拟运行失败，请查看高级技术详情。</div>}

      <div className="result-tabs" role="tablist" aria-label="模拟结果">
        {resultTabs.map(tab => (
          <button
            key={tab.id}
            type="button"
            className={activeResultTab === tab.id ? 'active' : ''}
            onClick={() => setActiveResultTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="runtime-result-sections single-result-panel">
        {activeResultTab === 'answer' && <section className="runtime-output-section runtime-answer-card">
          <div className="runtime-output-title">
            <strong>核心回答</strong>
            <span className="badge badge-muted">markdown</span>
          </div>
          <ExpandableMarkdown content={result.answer || result.error} maxChars={760} />
        </section>}

        {activeResultTab === 'evidence' && <section className="runtime-output-section">
          <div className="runtime-output-title">
            <strong>证据依据</strong>
            <span className="badge badge-muted">{result.evidence_used.length}</span>
          </div>
          <div className="runtime-evidence-list">
            {result.evidence_used.length > 0 ? (
              result.evidence_used.slice(0, 5).map((ev, index) => {
                const quote = String(ev.quote || '')
                return (
                  <div className={`runtime-evidence-item ${Number(ev.similarity_score || 0) >= 0.7 ? 'high-similarity' : ''}`} key={`${ev.chunk_id || index}-${index}`}>
                    <div className="evidence-meta">
                      <span className="badge badge-muted">chunk {String(ev.chunk_id ?? ev.chunk_index ?? 'n/a')}</span>
                      {ev.filename && <span className="badge badge-muted">{String(ev.filename)}</span>}
                      <span className={ev.retrieval_method === 'vector' ? 'badge badge-info' : 'badge badge-muted'}>
                        {String(ev.retrieval_method || 'evidence')}
                      </span>
                      {ev.similarity_score != null && (
                        <span className={Number(ev.similarity_score) >= 0.7 ? 'badge badge-success' : 'badge badge-muted'}>
                          similarity {Number(ev.similarity_score).toFixed(4)}
                        </span>
                      )}
                    </div>
                    <p>{quote.length > 220 ? `${quote.slice(0, 220)}...` : quote}</p>
                  </div>
                )
              })
            ) : (
              <p>未检索到证据片段。</p>
            )}
          </div>
          {result.files_used.length > 0 && (
            <div className="generated-file-list runtime-files-compact">
              {result.files_used.slice(0, 8).map(file => <span key={file}>{file}</span>)}
            </div>
          )}
        </section>}

        {activeResultTab === 'uncertainty' && <section className="runtime-output-section">
          <div className="runtime-output-title">
            <strong>不确定性 / 资料缺口</strong>
            <span className="badge badge-muted">{result.uncertainty_notes.length}</span>
          </div>
          {result.uncertainty_notes.length > 0 ? (
            <ul className="runtime-uncertainty-list">{result.uncertainty_notes.map(note => <li key={note}>{note}</li>)}</ul>
          ) : (
            <p>本次运行未标记额外不确定性。</p>
          )}
        </section>}

        {activeResultTab === 'safety' && <section className="runtime-output-section">
          <div className="runtime-output-title"><strong>安全边界</strong></div>
          <div className="status-row">
            <span className={safety.blocked ? 'badge badge-danger' : 'badge badge-success'}>
              {safety.blocked ? 'blocked' : 'passed'}
            </span>
            {(safety.risk_flags || []).map((flag: string) => <span className="badge badge-warning" key={flag}>{flag}</span>)}
          </div>
        </section>}

        {showTrace && activeResultTab === 'trace' && (
          <section className="runtime-output-section runtime-trace-box">
            <button className="btn-sm" onClick={onToggleTrace}>
              {traceOpen ? '收起技术记录' : '展开技术记录'}
            </button>
            {traceOpen && <pre className="preview-pre">{JSON.stringify(result.runtime_trace, null, 2)}</pre>}
          </section>
        )}
      </div>

      <div className="runtime-feedback-strip">
        <div>
          <strong>这次运行是否有帮助？</strong>
          <p>反馈会记录为修正线索，暂不会自动改写模拟能力。</p>
        </div>
        <div className="feedback-chip-row">
          {feedbackOptions.map(option => (
            <button
              key={option.value}
              type="button"
              className={feedbackRating === option.value ? 'active' : ''}
              onClick={() => {
                onFeedbackRating(option.value)
                onFeedbackExpanded(option.value !== 'good')
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        {feedbackExpanded && (
          <textarea
            rows={3}
            value={feedbackNote}
            onChange={e => onFeedbackNote(e.target.value)}
            placeholder="说明哪里不准、缺证据、不安全，或哪里不像这个人物。"
          />
        )}
        <button className="btn-secondary" onClick={onSubmitFeedback} disabled={feedbackBusy || !result.id}>
          {feedbackBusy ? '记录中' : '提交反馈'}
        </button>
      </div>
    </div>
  )
}

function CompareRuntimeView({
  result,
  onCopy,
  copied,
}: {
  result: SkillCompareRunResult;
  onCopy: (run: SkillWebsiteRun) => void;
  copied: string;
}) {
  return (
    <div className="compare-runtime-result slide-up">
      <div className="comparison-summary">
        <strong>差异总结</strong>
        <p>{result.comparison_summary}</p>
      </div>
      <div className="difference-table">
        <div className="difference-table-head">
          <strong>维度</strong>
          <span>思维模拟</span>
          <span>互动模拟</span>
        </div>
        {result.difference_table.map(row => (
          <div key={row.dimension}>
            <strong>{compareDimensionLabel(row.dimension)}</strong>
            <span>{row.nuwa}</span>
            <span>{row.colleague}</span>
          </div>
        ))}
      </div>
      <div className="runtime-recommendation">
        <strong>推荐使用场景</strong>
        <p>{result.recommendation}</p>
      </div>
      <div className="compare-runtime-grid">
        <RuntimeMiniResult title="思维模拟摘要" result={result.nuwa_result} onCopy={() => onCopy(result.nuwa_result)} copied={copied} />
        <RuntimeMiniResult title="互动模拟摘要" result={result.colleague_result} onCopy={() => onCopy(result.colleague_result)} copied={copied} />
      </div>
    </div>
  )
}

function RuntimeMiniResult({
  title,
  result,
  onCopy,
  copied,
}: {
  title: string;
  result: SkillWebsiteRun;
  onCopy: () => void;
  copied: string;
}) {
  const answerSummary = summarizeMarkdown(result.answer || result.error || '', '无输出')
  return (
    <div className="runtime-mini-result">
      <div className="runtime-result-head">
        <div>
          <span className={runtimeStatusBadgeClass(result.status)}>{result.status}</span>
          <h4>{title}</h4>
          <p>{runtimeModeLabel(result.runtime_mode)} · {result.evidence_used.length} 条证据</p>
        </div>
        <button className="btn-sm" onClick={onCopy}>{copied === 'website-runtime-answer' ? '已复制' : '复制'}</button>
      </div>
      <p className="runtime-mini-summary">{answerSummary}</p>
      <details className="runtime-full-output">
        <summary>展开完整结果</summary>
        <ExpandableMarkdown content={result.answer || result.error} maxChars={900} />
      </details>
    </div>
  )
}

function SkillPackageCard({
  title,
  generated,
  disabled,
  loading,
  validating,
  dryRunning,
  installing,
  runtimeBusy,
  onSpec,
  onGenerate,
  onValidate,
  onDryRun,
  onInstallInstructions,
  onGenerateRuntimeCases,
  onViewRuntimeCases,
  onOpenRuntimeResult,
  onDownload,
}: {
  title: string;
  generated?: GeneratedSkill;
  disabled: boolean;
  loading: boolean;
  validating: boolean;
  dryRunning: boolean;
  installing: boolean;
  runtimeBusy: boolean;
  onSpec: () => void;
  onGenerate: () => void;
  onValidate: () => void;
  onDryRun: () => void;
  onInstallInstructions: () => void;
  onGenerateRuntimeCases: () => void;
  onViewRuntimeCases: () => void;
  onOpenRuntimeResult: () => void;
  onDownload: () => void;
}) {
  return (
    <article className="skill-package-card hover-lift">
      <header>
        <div>
          <h4>{title}</h4>
          <p>{generated ? `Skill #${generated.id} · ${displaySkillLevel(null, generated)}` : '尚未生成兼容包'}</p>
        </div>
        <span className={generated?.compatible_skill_generated ? 'badge badge-success' : 'badge badge-muted'}>
          {generated?.compatible_skill_generated ? 'Skill Generated' : 'Not Generated'}
        </span>
      </header>

      <div className="package-file-preview">
        <strong>Generated files</strong>
        {generated?.generated_files?.length ? (
          <div className="generated-file-list">
            {generated.generated_files.slice(0, 8).map(file => <span key={file}>{file.split(/[\\/]/).pop()}</span>)}
          </div>
        ) : (
          <p>生成后可查看 README、Skill 文件、安装说明和 runtime 测试用例。</p>
        )}
      </div>

      {generated && (
        <div className="package-status-row">
          <span className={generated.validation_status ? 'badge badge-info' : 'badge badge-muted'}>{getValidationStatus(generated)}</span>
          <span className={generated.runtime_simulated ? 'badge badge-success' : 'badge badge-muted'}>
            {generated.runtime_simulated ? 'L5b Dry-run Simulated' : 'Dry-run pending'}
          </span>
          <span className={generated.l5c_passed ? 'badge badge-success' : 'badge badge-muted'}>
            {generated.l5c_passed ? 'L5c Actual Runtime Tested' : 'External L5c pending'}
          </span>
        </div>
      )}

      <div className="package-action-row">
        <button className="btn-secondary" onClick={onGenerate} disabled={disabled}>
          {loading ? <><span className="spinner" /> 生成中</> : '生成 Skill 包'}
        </button>
        <button className="btn-sm" onClick={onSpec}>查看文件 / 契约</button>
        <button className="btn-sm" onClick={onValidate} disabled={!generated || validating}>
          {validating ? '验证中' : '验证'}
        </button>
        <button className="btn-sm" onClick={onDryRun} disabled={!generated || dryRunning}>
          {dryRunning ? 'Dry-run 中' : 'Dry-run'}
        </button>
        <button className="btn-sm" onClick={onDownload} disabled={!generated?.compatible_skill_generated}>
          下载 ZIP
        </button>
        <button className="btn-sm" onClick={onInstallInstructions} disabled={!generated || installing}>
          {installing ? '生成中' : '安装说明'}
        </button>
        <button className="btn-sm" onClick={onGenerateRuntimeCases} disabled={!generated || runtimeBusy}>
          {runtimeBusy ? '处理中' : '生成 Runtime 测试用例'}
        </button>
        <button className="btn-sm" onClick={onViewRuntimeCases} disabled={!generated || runtimeBusy}>
          查看测试用例
        </button>
        <button className="btn-sm" onClick={onOpenRuntimeResult} disabled={!generated}>
          回填 / 评估外部结果
        </button>
      </div>
    </article>
  )
}

function SkillEngineCard({
  title, subtitle, status, generated, runtimeRuns,
}: {
  title: string;
  subtitle: string;
  status: SkillIntegrationStatus | null;
  generated?: GeneratedSkill;
  runtimeRuns: SkillWebsiteRun[];
}) {
  const level = displaySkillLevel(status, generated)
  const validationStatus = getValidationStatus(generated)
  const lastRuntimeRun = runtimeRuns[0]
  const websiteRuntimeStatus = !lastRuntimeRun
    ? 'Not run'
    : lastRuntimeRun.status === 'success'
      ? 'Last run success'
      : lastRuntimeRun.status === 'blocked'
        ? 'Last run blocked'
        : 'Last run failed'
  return (
    <article className="skill-engine-card hover-lift">
      <header>
        <div>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        <span className={status?.available ? 'badge badge-success' : 'badge badge-muted'}>
          {status?.available ? 'repo ready' : 'fallback'}
        </span>
      </header>
      <div className="skill-level-row">
        {['L3', 'L4', 'L5a', 'L5b', 'L5c'].map(l => (
          <span key={l} className={skillLevelRank(level) >= skillLevelRank(l) ? 'active' : ''}>{l}</span>
        ))}
      </div>
      <div className="status-matrix">
        <span>当前层级</span><strong>{level}</strong>
        <span>验证状态</span><strong>{validationStatus}</strong>
        <span>仓库导入</span><strong>{status?.installed ? '是' : '否'}</strong>
        <span>契约解析</span><strong>{status?.available ? '可读取' : '不可用'}</strong>
        <span>兼容包</span><strong>{generated?.compatible_skill_generated ? '已生成' : '未生成'}</strong>
        <span>结构分数</span><strong>{generated ? `${generated.validation_score || 0}/100` : '未验证'}</strong>
        <span>Dry-run</span><strong>{generated?.runtime_simulated ? '已模拟' : '未模拟'}</strong>
        <span>L5c 实测</span><strong>{generated?.l5c_passed ? `${generated.l5c_runtime_target} · ${generated.l5c_score}/100` : '未回填通过'}</strong>
        <span>Website Runtime</span><strong>{websiteRuntimeStatus}</strong>
        <span>站内运行数</span><strong>{runtimeRuns.length}</strong>
        <span>最近站内运行</span><strong>{lastRuntimeRun ? formatDateTime(lastRuntimeRun.created_at) : '未运行'}</strong>
      </div>
      {generated && (
        <p className="skill-runtime-note">
          Website Runtime = 站内 {lastRuntimeRun?.model_provider || '当前 LLM provider'} 读取 Skill 包执行；L5c = 外部 runtime 测试回填。
        </p>
      )}
      {generated && (
        <div className="validation-score">
          <div style={{ width: `${Math.max(0, Math.min(100, generated.validation_score || 0))}%` }} />
        </div>
      )}
      {generated && (
        <div className="generated-files-panel">
          <strong>最近生成文件</strong>
          <div className="generated-file-list">
            {generated.generated_files.slice(0, 8).map(file => <span key={file}>{file.split(/[\\/]/).pop()}</span>)}
          </div>
        </div>
      )}
      {generated && (
        <div className="validation-details">
          {(generated.validation_passed_checks || []).slice(0, 3).map(item => <span className="badge badge-success" key={item}>{item}</span>)}
          {(generated.validation_errors || []).slice(0, 3).map(item => <span className="badge badge-danger" key={item}>{item}</span>)}
          {(generated.validation_warnings || []).slice(0, 3).map(item => <span className="badge badge-warning" key={item}>{item}</span>)}
        </div>
      )}
      {generated?.runtime_simulated && !generated.l5c_passed && (
        <p className="skill-runtime-note">Dry-run 是站内模拟，不等于真实 runtime。L5c 需要外部 runtime 实测结果，系统只记录用户回填，不自动访问 Codex / Claude Code / Hermes。</p>
      )}
      {generated?.l5c_passed && (
        <p className="skill-runtime-note success">L5c Actual Runtime Tested：来自用户回填的外部 runtime 测试结果，result_id={generated.l5c_result_id || 'n/a'}。</p>
      )}
      {status?.error && <p className="skill-error">{status.error}</p>}
    </article>
  )
}

function displaySkillLevel(status: SkillIntegrationStatus | null, generated?: GeneratedSkill): string {
  if (generated?.l5c_passed) return 'L5c actual runtime tested'
  if (generated?.runtime_simulated) return 'L5b dry-run simulated'
  if (generated?.validation_status === 'L5-structure-validated') return 'L5a structure validated'
  if (generated?.compatible_skill_generated) return 'L4 compatible generated'
  return status?.available ? 'L3 repo imported' : 'L0 mentioned'
}

function skillLevelRank(level: string): number {
  if (level.includes('L5c')) return 5
  if (level.includes('L5b')) return 4
  if (level.includes('L5a')) return 3
  if (level.includes('L4')) return 2
  if (level.includes('L3')) return 1
  return 0
}

function getValidationStatus(generated?: GeneratedSkill): string {
  if (!generated) return 'Not Generated'
  if (generated.l5c_passed) return 'Runtime Tested'
  if (generated.runtime_simulated) return 'Dry Run Passed'
  if (generated.validation_status === 'L5-structure-validated') return 'Structure Validated'
  return 'Generated'
}

function runtimeStatusBadgeClass(status: string): string {
  if (status === 'success') return 'badge badge-success'
  if (status === 'blocked') return 'badge badge-warning'
  if (status === 'error') return 'badge badge-danger'
  return 'badge badge-muted'
}

function SpecList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="spec-list">
      <h4>{title}</h4>
      {items.length > 0 ? (
        <ul>{items.map(item => <li key={item}>{item}</li>)}</ul>
      ) : (
        <p>暂无</p>
      )}
    </div>
  )
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString('zh-CN')
}

function formatDateTime(date: string): string {
  return new Date(date).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
