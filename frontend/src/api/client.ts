const BASE = '/api';

function extractErrorMessage(errBody: any, status: number, statusText: string): string {
  if (!errBody) return `请求失败 (HTTP ${status}: ${statusText})`;
  // FastAPI 422: detail is an array of {loc, msg, type}
  if (Array.isArray(errBody.detail)) {
    const msgs = errBody.detail.map((d: any) => d.msg || JSON.stringify(d));
    return `参数校验失败 (HTTP 422): ${msgs.join('; ')}`;
  }
  return errBody.detail || errBody.error || `请求失败 (HTTP ${status}: ${statusText})`;
}

export class ApiError extends Error {
  status: number;
  statusText: string;
  body: any;

  constructor(status: number, statusText: string, body: any) {
    super(extractErrorMessage(body, status, statusText));
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

export function isNotFoundError(err: unknown): boolean {
  if (err instanceof ApiError) return err.status === 404;
  if (err instanceof Error) return /\bHTTP 404\b|Not Found/i.test(err.message);
  return false;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new ApiError(res.status, res.statusText, err);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

async function readResponseBody(res: Response): Promise<any> {
  const text = await res.text().catch(() => '');
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export interface EvidenceItem {
  chunk_index: number;
  chunk_id?: number;
  filename?: string;
  retrieval_method?: 'vector' | 'keyword';
  similarity_score?: number | null;
  quote: string;
}

export interface EvidenceClaim {
  claim: string;
  evidence: EvidenceItem[];
  confidence_score: number;
  data_gap: string | null;
  contradiction: string | null;
}

export interface EvidenceModule {
  module_name: string;
  data_sufficient: boolean;
  claims: EvidenceClaim[];
}

export type EvidenceMap = Record<string, EvidenceModule>;

export interface AnalysisQuality {
  total_chars: number;
  document_count: number;
  chunk_count: number;
  evidence_coverage: number;
  avg_confidence: number;
  diversity_score: number;
  has_chat_corpus: boolean;
  has_long_text: boolean;
  has_multi_emotion: boolean;
  suitability_level: string;
  suitability_label: string;
  distinct_sources?: number;
  parsers?: string[];
}

export interface Profile {
  id: number;
  name: string;
  description: string;
  relationship_type: string;
  created_at: string;
  updated_at: string;
  document_count: number;
  chunk_count: number;
  total_chars: number;
  has_analysis: boolean;
  latest_portrait?: string;
  latest_style_card?: string;
  evidence_json?: string;
  analysis_quality?: AnalysisQuality;
}

export interface DataSufficiency {
  level: 'none' | 'very_low' | 'low' | 'medium' | 'high';
  label: string;
  description: string;
  sim_suitable: boolean;
  total_chars: number;
  chunk_count: number;
}

export interface Document {
  id: number;
  profile_id: number;
  filename: string;
  file_type: string;
  content_type: string;
  char_count: number;
  chunk_count: number;
  parser?: string;
  parse_status?: string;
  uploaded_at: string;
}

export interface MineruStatus {
  installed: boolean;
  command: string | null;
  version_or_help: string | null;
  error: string | null;
  enabled: boolean;
  backend: string;
  method: string;
  lang: string;
  formula: boolean;
  table: boolean;
  image_analysis: boolean;
  timeout_seconds: number;
}

export interface Analysis {
  id: number;
  profile_id: number;
  portrait_report: string;
  style_card: string;
  evidence_json?: string | null;
  total_chunks: number;
  total_chars: number;
  model_used: string;
  created_at: string;
}

export interface ChatMessage {
  id: number;
  profile_id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export type PipelineStepStatusName = 'pending' | 'running' | 'done' | 'warning' | 'failed';

export interface ProfilePipelineOptions {
  run_analysis?: boolean;
  generate_nuwa_skill?: boolean;
  generate_colleague_skill?: boolean;
  validate_skills?: boolean;
  prepare_website_runtime?: boolean;
  run_dry_run?: boolean;
  generate_runtime_testcases?: boolean;
}

export interface ProfilePipelineStepStatus {
  status: PipelineStepStatusName | string;
  detail: string;
  skill_id?: number | null;
  analysis_id?: number | null;
  model_used?: string | null;
}

export interface ProfilePipelineResult {
  profile_id: number;
  pipeline_status: 'completed' | 'partial' | 'failed' | 'need_upload' | string;
  analysis_ready: boolean;
  evidence_ready: boolean;
  skills_ready: boolean;
  runtime_ready: boolean;
  nuwa_skill_id?: number | null;
  colleague_skill_id?: number | null;
  analysis_status: ProfilePipelineStepStatus;
  evidence_status: ProfilePipelineStepStatus;
  nuwa_skill_status: ProfilePipelineStepStatus;
  colleague_skill_status: ProfilePipelineStepStatus;
  validation_status: ProfilePipelineStepStatus;
  website_runtime_ready: boolean;
  warnings: string[];
  errors: string[];
  next_actions: string[];
}

// Profile APIs
export const createProfile = (data: { name: string; description: string; relationship_type: string }) =>
  request<Profile>('/profiles', { method: 'POST', body: JSON.stringify(data) });

export const listProfiles = () => request<Profile[]>('/profiles');

export const getProfile = (id: number) => request<Profile>(`/profiles/${id}`);

// Document APIs
export const uploadDocument = (profileId: number, file: File) => {
  const form = new FormData();
  form.append('file', file);
  return fetch(`${BASE}/profiles/${profileId}/documents`, { method: 'POST', body: form }).then(async (res) => {
    if (!res.ok) {
      const err = await res.json().catch(() => null);
      throw new ApiError(res.status, res.statusText, err);
    }
    return res.json();
  });
};

export const listDocuments = (profileId: number) => request<Document[]>(`/profiles/${profileId}/documents`);

// Analysis APIs
export const analyzeProfile = (profileId: number) =>
  request<Analysis>(`/profiles/${profileId}/analyze`, { method: 'POST' });

function createNeedUploadPipelineResult(profileId: number): ProfilePipelineResult {
  return {
    profile_id: profileId,
    pipeline_status: 'need_upload',
    analysis_ready: false,
    evidence_ready: false,
    skills_ready: false,
    runtime_ready: false,
    nuwa_skill_id: null,
    colleague_skill_id: null,
    analysis_status: { status: 'pending', detail: '等待资料上传' },
    evidence_status: { status: 'pending', detail: '等待资料上传' },
    nuwa_skill_status: { status: 'pending', detail: '等待画像完成' },
    colleague_skill_status: { status: 'pending', detail: '等待画像完成' },
    validation_status: { status: 'pending', detail: '等待 Skill 生成' },
    website_runtime_ready: false,
    warnings: ['请先上传资料'],
    errors: [],
    next_actions: ['请先上传资料后再开始分析。'],
  };
}

async function runLegacyPipelineFallback(
  profileId: number,
  options?: ProfilePipelineOptions,
  notFoundBody?: any,
): Promise<ProfilePipelineResult> {
  console.debug('[Echo Profile] pipeline analyze fallback check', {
    profileId,
    missingUrl: `${BASE}/profiles/${profileId}/pipeline/analyze`,
    fallbackUrl: `${BASE}/profiles/${profileId}/analyze`,
  });

  let profile: Profile;
  try {
    profile = await getProfile(profileId);
  } catch (err) {
    if (isNotFoundError(err)) {
      throw new ApiError(404, 'Not Found', notFoundBody || { detail: '人物档案不存在' });
    }
    throw err;
  }

  if (!profile.chunk_count) {
    console.debug('[Echo Profile] pipeline analyze fallback need_upload', {
      profileId,
      chunkCount: profile.chunk_count,
    });
    return createNeedUploadPipelineResult(profileId);
  }

  const warnings = ['当前运行后端未暴露 pipeline/analyze，已降级使用 legacy analyze 接口。'];
  const analysis = await analyzeProfile(profileId);
  const evidenceReady = Boolean(analysis.evidence_json);
  let nuwaSkillId: number | null = null;
  let colleagueSkillId: number | null = null;
  let nuwaStatus: ProfilePipelineStepStatus = { status: 'pending', detail: '未请求生成 Nuwa Skill' };
  let colleagueStatus: ProfilePipelineStepStatus = { status: 'pending', detail: '未请求生成 Colleague Skill' };

  if (options?.generate_nuwa_skill !== false) {
    try {
      const nuwa = await generateNuwaSkill(profileId);
      nuwaSkillId = nuwa.skill?.id ?? null;
      nuwaStatus = {
        status: nuwa.generated && nuwaSkillId ? 'done' : 'warning',
        detail: nuwa.detail || nuwa.error || (nuwa.generated ? 'Nuwa Skill 已生成' : 'Nuwa Skill 生成未完成'),
        skill_id: nuwaSkillId,
      };
      if (!nuwa.generated) warnings.push(nuwa.detail || nuwa.error || 'Nuwa Skill 生成未完成');
    } catch (err: any) {
      nuwaStatus = { status: 'warning', detail: `Nuwa Skill 生成失败：${err.message}` };
      warnings.push(nuwaStatus.detail);
    }
  }

  if (options?.generate_colleague_skill !== false) {
    try {
      const colleague = await generateColleagueSkill(profileId);
      colleagueSkillId = colleague.skill?.id ?? null;
      colleagueStatus = {
        status: colleague.generated && colleagueSkillId ? 'done' : 'warning',
        detail: colleague.detail || colleague.error || (colleague.generated ? 'Colleague Skill 已生成' : 'Colleague Skill 生成未完成'),
        skill_id: colleagueSkillId,
      };
      if (!colleague.generated) warnings.push(colleague.detail || colleague.error || 'Colleague Skill 生成未完成');
    } catch (err: any) {
      colleagueStatus = { status: 'warning', detail: `Colleague Skill 生成失败：${err.message}` };
      warnings.push(colleagueStatus.detail);
    }
  }

  const skillsReady = Boolean(nuwaSkillId && colleagueSkillId);
  const runtimeReady = Boolean(nuwaSkillId || colleagueSkillId);

  return {
    profile_id: profileId,
    pipeline_status: warnings.length || !skillsReady || !evidenceReady ? 'partial' : 'completed',
    analysis_ready: Boolean(analysis.portrait_report && analysis.style_card),
    evidence_ready: evidenceReady,
    skills_ready: skillsReady,
    runtime_ready: runtimeReady,
    nuwa_skill_id: nuwaSkillId,
    colleague_skill_id: colleagueSkillId,
    analysis_status: {
      status: 'done',
      detail: '证据画像已生成',
      analysis_id: analysis.id,
      model_used: analysis.model_used,
    },
    evidence_status: {
      status: evidenceReady ? 'done' : 'warning',
      detail: evidenceReady ? '证据链已生成' : '画像完成，但 evidence_map 缺失或为空',
    },
    nuwa_skill_status: nuwaStatus,
    colleague_skill_status: colleagueStatus,
    validation_status: { status: 'pending', detail: 'legacy fallback 未执行结构验证' },
    website_runtime_ready: runtimeReady,
    warnings,
    errors: [],
    next_actions: runtimeReady
      ? ['可进入模拟实验台。']
      : ['画像已完成，但 Skill 未完全准备；可展开高级技术详情查看原因。'],
  };
}

export const runProfilePipeline = async (profileId: number, options?: ProfilePipelineOptions): Promise<ProfilePipelineResult> => {
  const path = `/profiles/${profileId}/pipeline/analyze`;
  const url = `${BASE}${path}`;
  console.debug('[Echo Profile] pipeline analyze request', {
    profileId,
    url,
    hasBody: true,
  });
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options || {}),
  });
  const body = await readResponseBody(res);
  console.debug('[Echo Profile] pipeline analyze response', {
    profileId,
    url,
    status: res.status,
    body,
  });
  if (!res.ok) {
    if (res.status === 404) {
      return runLegacyPipelineFallback(profileId, options, body);
    }
    throw new ApiError(res.status, res.statusText, body);
  }
  return body as ProfilePipelineResult;
};

export const listAnalyses = (profileId: number) => request<Analysis[]>(`/profiles/${profileId}/analysis`);

// Chat APIs
export type ChatMode = 'daily_chat' | 'deep_analysis' | 'comfort' | 'advice' | 'style_clone' | 'communication_strategy';

export const sendMessage = (profileId: number, message: string, mode: ChatMode = 'daily_chat') =>
  request<{
    reply: string;
    profile_name: string;
    retrieved_count: number;
    model_used: string;
    retrieval_method: 'vector' | 'keyword';
    retrieved_chunks: Array<Record<string, unknown>>;
  }>(
    `/profiles/${profileId}/chat`,
    { method: 'POST', body: JSON.stringify({ message, mode }) }
  );

export const listChatMessages = (profileId: number) =>
  request<ChatMessage[]>(`/profiles/${profileId}/chat`);

// Health
export const checkHealth = () => request<{ status: string }>('/health').catch(() => null);

// Config status (safe, no API key)
export interface ConfigStatus {
  llm_provider: string;
  is_mock: boolean;
  analysis_model: string;
  chat_model: string;
  base_url: string;
  has_api_key: boolean;
  timeout_seconds: number;
}
export const getConfigStatus = () => request<ConfigStatus>('/config/status');

// Data Sufficiency
export const getSufficiency = (profileId: number) =>
  request<DataSufficiency>(`/profiles/${profileId}/sufficiency`);

// Export
export interface SkillCardExport {
  profile_id: number;
  profile_name: string;
  format: string;
  filename: string;
  content: string;
}
export const exportSkillCard = (profileId: number) =>
  request<SkillCardExport>(`/profiles/${profileId}/export/skill-card`);

export interface DatasetExport {
  profile_id: number;
  profile_name: string;
  format: string;
  filename: string;
  total_records: number;
  records: Record<string, unknown>[];
}
export const exportDataset = (profileId: number) =>
  request<DatasetExport>(`/profiles/${profileId}/export/dataset`);

// MinerU status
export const getMineruStatus = () =>
  request<MineruStatus>('/integrations/mineru/status');

// mem0 status
export interface Mem0Status {
  installed: boolean;
  enabled: boolean;
  available: boolean;
  provider: string;
  error: string | null;
  detail: string;
}
export const getMem0Status = () =>
  request<Mem0Status>('/integrations/mem0/status');

// Vector retrieval status
export interface VectorStatus {
  installed: boolean;
  enabled: boolean;
  available: boolean;
  provider: string;
  embedding_model: string;
  error: string | null;
  detail: string;
  collection?: string | null;
  points_count: number;
  indexed: boolean;
}
export const getVectorStatus = (profileId?: number) =>
  request<VectorStatus>(`/integrations/vector/status${profileId ? `?profile_id=${profileId}` : ''}`);

export interface VectorRebuildResult {
  indexed: number;
  error: string | null;
  detail: string;
}
export const rebuildVectorIndex = (profileId: number) =>
  request<VectorRebuildResult>(`/profiles/${profileId}/vector/rebuild`, { method: 'POST' });

export interface VectorSearchResult {
  query: string;
  retrieval_method: 'vector' | 'keyword';
  results: Array<Record<string, unknown>>;
  total: number;
}
export const searchVectorChunks = (profileId: number, query: string) =>
  request<VectorSearchResult>(`/profiles/${profileId}/vector/search?query=${encodeURIComponent(query)}`);

// Skill Foundry integrations
export interface SkillIntegrationStatus {
  name: 'nuwa' | 'colleague' | string;
  installed: boolean;
  available: boolean;
  source_repo: string;
  source_path: string;
  error: string | null;
  detail: string;
  level: string;
  level_label: string;
}

export interface SkillSpec {
  name: string;
  source_repo: string;
  source_path: string;
  project_name: string;
  description: string;
  skill_purpose: string[];
  input_requirements: string[];
  workflow: string[];
  output_contract: string[];
  runtime_hosts: string[];
  limitations: string[];
  raw_files_read: string[];
}

export interface GeneratedSkill {
  id: number;
  profile_id: number;
  skill_type: 'nuwa' | 'colleague' | string;
  source_repo: string;
  source_path: string;
  output_path: string;
  generated_files: string[];
  status: string;
  repo_imported: boolean;
  spec_parsed: boolean;
  compatible_skill_generated: boolean;
  original_cli_invoked: boolean;
  validation_status: string;
  validation_score: number;
  validation_passed_checks: string[];
  validation_errors: string[];
  validation_warnings: string[];
  runtime_simulated: boolean;
  actual_runtime_invoked: boolean;
  runtime_test_output_path: string;
  install_instructions_path: string;
  last_validated_at?: string | null;
  l5c_runtime_target: string;
  l5c_passed: boolean;
  l5c_score: number;
  l5c_result_id?: number | null;
  l5c_validated_at?: string | null;
  error: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface SkillGenerateResult {
  generated: boolean;
  skill: GeneratedSkill | null;
  detail: string;
  error: string | null;
}

export interface SkillValidationResult {
  validation_score: number;
  runtime_ready: boolean;
  level: string;
  passed_checks: string[];
  warnings: string[];
  errors: string[];
  runtime_simulated: boolean;
  actual_runtime_invoked: boolean;
  install_instructions_path: string;
  simulated_output?: string | null;
  used_files: string[];
  error?: string | null;
}

export const getNuwaStatus = () =>
  request<SkillIntegrationStatus>('/integrations/nuwa/status');
export const getNuwaSpec = () =>
  request<SkillSpec>('/integrations/nuwa/spec');
export const getColleagueStatus = () =>
  request<SkillIntegrationStatus>('/integrations/colleague/status');
export const getColleagueSpec = () =>
  request<SkillSpec>('/integrations/colleague/spec');
export const listGeneratedSkills = (profileId: number) =>
  request<GeneratedSkill[]>(`/profiles/${profileId}/skills`);
export const generateNuwaSkill = (profileId: number) =>
  request<SkillGenerateResult>(`/profiles/${profileId}/skills/nuwa/generate`, { method: 'POST' });
export const generateColleagueSkill = (profileId: number) =>
  request<SkillGenerateResult>(`/profiles/${profileId}/skills/colleague/generate`, { method: 'POST' });
export const generatedSkillDownloadUrl = (profileId: number, skillId: number) =>
  `${BASE}/profiles/${profileId}/skills/${skillId}/download`;
export const validateGeneratedSkill = (profileId: number, skillId: number) =>
  request<SkillValidationResult>(`/profiles/${profileId}/skills/${skillId}/validate`, { method: 'POST' });
export const dryRunGeneratedSkill = (profileId: number, skillId: number, testPrompt?: string) =>
  request<SkillValidationResult>(`/profiles/${profileId}/skills/${skillId}/dry-run`, {
    method: 'POST',
    body: JSON.stringify({ test_prompt: testPrompt || '请说明你会如何使用 evidence_policy，并指出资料不足时应该如何回答。' }),
  });
export const getSkillInstallInstructions = (profileId: number, skillId: number, target: string = 'codex') =>
  request<SkillValidationResult>(`/profiles/${profileId}/skills/${skillId}/install-instructions?target=${encodeURIComponent(target)}`);

export interface RuntimeTestCasesResult {
  runtime_target: string;
  markdown_path: string;
  json_path: string;
  test_cases: Array<{
    case_id: string;
    title: string;
    prompt: string;
    expected_behavior: string;
    pass_criteria: string[];
    risk_flags: string[];
  }>;
  warnings: string[];
}

export interface RuntimeResultSubmission {
  runtime_target: string;
  tester_note: string;
  test_output_text: string;
  evidence_of_runtime: string;
}

export interface RuntimeResult {
  id: number;
  generated_skill_id: number;
  profile_id: number;
  skill_type: string;
  runtime_target: string;
  tester_note: string;
  test_output_text: string;
  score: number;
  passed: boolean;
  failed_cases: string[];
  warnings: string[];
  evidence_of_runtime: string;
  created_at: string;
}

export interface RuntimeEvaluationResult {
  result_id: number | null;
  score: number;
  passed: boolean;
  failed_cases: string[];
  warnings: string[];
  recommended_fix: string;
  can_mark_l5c: boolean;
  judgeable_cases: number;
  safety_boundary_passed: boolean;
  evidence_policy_passed: boolean;
}

export const generateRuntimeTestCases = (profileId: number, skillId: number, runtimeTarget: string = 'codex') =>
  request<RuntimeTestCasesResult>(`/profiles/${profileId}/skills/${skillId}/runtime-testcases`, {
    method: 'POST',
    body: JSON.stringify({ runtime_target: runtimeTarget }),
  });
export const getRuntimeTestCases = (profileId: number, skillId: number, runtimeTarget: string = 'codex') =>
  request<RuntimeTestCasesResult>(`/profiles/${profileId}/skills/${skillId}/runtime-testcases?runtime_target=${encodeURIComponent(runtimeTarget)}`);
export const submitRuntimeResult = (profileId: number, skillId: number, payload: RuntimeResultSubmission) =>
  request<RuntimeResult>(`/profiles/${profileId}/skills/${skillId}/runtime-results`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
export const listRuntimeResults = (profileId: number, skillId: number) =>
  request<RuntimeResult[]>(`/profiles/${profileId}/skills/${skillId}/runtime-results`);
export const evaluateRuntimeResult = (profileId: number, skillId: number, payload: RuntimeResultSubmission) =>
  request<RuntimeEvaluationResult>(`/profiles/${profileId}/skills/${skillId}/runtime-results/evaluate`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

export type SkillRuntimeMode =
  | 'nuwa_thinking'
  | 'colleague_interaction'
  | 'compare'
  | 'evidence_check'
  | 'uncertainty_check';

export interface SkillWebsiteRun {
  id: number | null;
  profile_id: number;
  generated_skill_id: number;
  skill_type: string;
  runtime_mode: SkillRuntimeMode | string;
  user_prompt: string;
  answer: string;
  model_provider: string;
  files_used: string[];
  evidence_used: Array<Record<string, any>>;
  uncertainty_notes: string[];
  safety_check: Record<string, any>;
  runtime_trace: Record<string, any>;
  status: 'success' | 'error' | 'blocked' | string;
  error: string | null;
  created_at: string;
}

export interface SkillCompareRunResult {
  nuwa_result: SkillWebsiteRun;
  colleague_result: SkillWebsiteRun;
  comparison_summary: string;
  difference_table: Array<{
    dimension: string;
    nuwa: string;
    colleague: string;
  }>;
  recommendation: string;
}

export interface SkillRuntimeFeedbackPayload {
  rating: 'good' | 'inaccurate' | 'unsafe' | 'not_like_person' | 'missing_evidence';
  note: string;
}

export interface SkillRuntimeFeedbackResult {
  id: number;
  run_id: number;
  profile_id: number;
  generated_skill_id: number;
  rating: string;
  note: string;
  correction_history_appended: boolean;
  created_at: string;
}

export const runWebsiteSkill = (
  profileId: number,
  skillId: number,
  payload: { user_prompt: string; runtime_mode: SkillRuntimeMode },
) =>
  request<SkillWebsiteRun>(`/profiles/${profileId}/skills/${skillId}/run`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
export const listWebsiteSkillRuns = (profileId: number, skillId: number) =>
  request<SkillWebsiteRun[]>(`/profiles/${profileId}/skills/${skillId}/runs`);
export const getWebsiteSkillRun = (profileId: number, skillId: number, runId: number) =>
  request<SkillWebsiteRun>(`/profiles/${profileId}/skills/${skillId}/runs/${runId}`);
export const compareWebsiteSkills = (
  profileId: number,
  payload: { user_prompt: string; nuwa_skill_id: number; colleague_skill_id: number },
) =>
  request<SkillCompareRunResult>(`/profiles/${profileId}/skills/compare-run`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
export const submitWebsiteSkillRunFeedback = (
  profileId: number,
  skillId: number,
  runId: number,
  payload: SkillRuntimeFeedbackPayload,
) =>
  request<SkillRuntimeFeedbackResult>(`/profiles/${profileId}/skills/${skillId}/runs/${runId}/feedback`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });

// Memory operations
export interface MemoryRebuildResult {
  stored: number;
  error: string | null;
}
export const rebuildMemories = (profileId: number) =>
  request<MemoryRebuildResult>(`/profiles/${profileId}/memory/rebuild`, { method: 'POST' });

export interface MemorySearchResult {
  results: { id: string; memory: string; score: number | null }[];
  query: string;
  total: number;
}
export const searchMemories = (profileId: number, query: string, limit: number = 5) =>
  request<MemorySearchResult>(`/profiles/${profileId}/memory/search?q=${encodeURIComponent(query)}&limit=${limit}`);

// Document management
export interface DocumentPreview {
  document_id: number;
  filename: string;
  parser: string | null;
  parse_status: string | null;
  char_count: number;
  preview_text: string;
  source: string;
}
export const deleteDocument = (profileId: number, documentId: number) =>
  request<{ message: string; detail: string }>(`/profiles/${profileId}/documents/${documentId}`, { method: 'DELETE' });

export const rebuildChunks = (profileId: number) =>
  request<{ message: string; detail: string }>(`/profiles/${profileId}/rebuild-chunks`, { method: 'POST' });

export const previewDocument = (profileId: number, documentId: number) =>
  request<DocumentPreview>(`/profiles/${profileId}/documents/${documentId}/preview`);

// SFT Export
export interface SFTExport {
  profile_id: number;
  profile_name: string;
  format: string;
  filename: string;
  total_records: number;
  content: string;
}
export const exportSFT = (profileId: number) =>
  request<SFTExport>(`/profiles/${profileId}/export/sft`);

// Analysis Quality
export interface QualityResponse {
  profile_id: number;
  profile_name: string;
  quality: AnalysisQuality;
  sample_chunks: Array<{
    chunk_id: number;
    document_id: number;
    filename: string;
    chunk_index: number;
    content_preview: string;
    char_count: number;
    parser: string;
  }>;
}
export const getAnalysisQuality = (profileId: number) =>
  request<QualityResponse>(`/profiles/${profileId}/quality`);

// Export Analysis Report
export interface AnalysisReportExport {
  profile_id: number;
  profile_name: string;
  format: string;
  filename: string;
  content: string;
}
export const exportAnalysisReport = (profileId: number) =>
  request<AnalysisReportExport>(`/profiles/${profileId}/export/analysis-report`);
