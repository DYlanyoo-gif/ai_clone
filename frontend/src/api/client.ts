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

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    throw new Error(extractErrorMessage(err, res.status, res.statusText));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
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
      throw new Error(extractErrorMessage(err, res.status, res.statusText));
    }
    return res.json();
  });
};

export const listDocuments = (profileId: number) => request<Document[]>(`/profiles/${profileId}/documents`);

// Analysis APIs
export const analyzeProfile = (profileId: number) =>
  request<Analysis>(`/profiles/${profileId}/analyze`, { method: 'POST' });

export const listAnalyses = (profileId: number) => request<Analysis[]>(`/profiles/${profileId}/analysis`);

// Chat APIs
export type ChatMode = 'daily_chat' | 'deep_analysis' | 'comfort' | 'advice' | 'style_clone' | 'communication_strategy';

export const sendMessage = (profileId: number, message: string, mode: ChatMode = 'daily_chat') =>
  request<{ reply: string; profile_name: string; retrieved_count: number; model_used: string }>(
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
