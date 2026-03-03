/**
 * Typed API client for the Code Wiki backend.
 * All methods map 1:1 to openapi.yaml operationIds.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/v1";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Pagination {
  page: number;
  limit: number;
  total_pages: number;
  total_items: number;
}

export interface PipelineProgress {
  current_step?: number;
  step_label?: string;
  step_detail?: string;
  stats?: {
    files_scanned?: number;
    loc?: number;
    languages?: string[];
    entities_found?: number;
    modules_detected?: number;
    agents_completed?: number;
    agents_total?: number;
    neo4j_nodes?: number;
    neo4j_edges?: number;
    neo4j_unresolved?: number;
    pages_generated?: number;
    pages_total?: number;
  };
  started_at?: string;
  elapsed_seconds?: number;
}

export interface AgentProgressEvent {
  type: 'agent_progress';
  agent: string;
  status: 'running' | 'complete';
  detail: string;
  timestamp: number;
}

export interface StepProgressEvent extends PipelineProgress {
  type: 'step_progress';
}

export interface DoneEvent {
  type: 'done';
  status: 'ready' | 'error';
  error?: string;
}

export type SSEEvent = AgentProgressEvent | StepProgressEvent | DoneEvent | PipelineProgress;

export interface Repository {
  id: string;
  url: string;
  name: string;
  owner: string;
  primary_languages: string[];
  size_lines?: number;
  size_files?: number;
  last_analyzed_commit?: string;
  last_analyzed_at?: string;
  branch?: string;
  status: "pending" | "analyzing" | "ready" | "error";
  error_message?: string;
  progress?: PipelineProgress;
  access_level?: "public" | "private";
  created_at: string;
  updated_at: string;
}

export interface Wiki {
  id: string;
  repository_id: string;
  home_page_id?: string;
  structure_version?: number;
  module_count?: number;
  page_count?: number;
  status: "generating" | "ready" | "updating";
  generated_at?: string;
  updated_at?: string;
}

export interface WikiPage {
  id: string;
  wiki_id?: string;
  page_type: "home" | "module" | "getting_started" | "function_index" | "glossary" | "api_reference";
  title: string;
  slug: string;
  content: Record<string, unknown>;
  related_page_ids: string[];
  source_files: string[];
  commit_hash?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Module {
  id: string;
  wiki_id?: string;
  wiki_page_id?: string;
  name: string;
  slug: string;
  file_paths: string[];
  file_count?: number;
  line_count?: number;
  description?: string;
  detection_confidence?: number;
  dependencies_module_ids: string[];
  created_at?: string;
}

export interface CodeEntityRelationships {
  calls: string[];
  imports: string[];
  inherits_from: string[];
}

export interface CodeEntity {
  id: string;
  module_id?: string;
  entity_type: "function" | "class" | "method" | "module" | "file" | "variable";
  name: string;
  qualified_name: string;
  file_path: string;
  line_number: number;
  signature?: string;
  description?: string;
  docstring?: string;
  visibility?: "public" | "private" | "protected";
  relationships?: CodeEntityRelationships;
}

export interface ChatMessageReference {
  type: "wiki_page" | "code_entity" | "file";
  id: string;
  title: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  references: ChatMessageReference[];
}

export interface ChatConversation {
  id: string;
  user_id?: string;
  repository_id: string;
  messages: ChatMessage[];
  created_at?: string;
  updated_at?: string;
}

export interface UpdateEvent {
  id: string;
  repository_id: string;
  commit_hash: string;
  changed_files: string[];
  affected_module_ids: string[];
  status: "pending" | "processing" | "completed" | "failed";
  started_at?: string;
  completed_at?: string;
  error_message?: string;
}

export interface DiagramNode {
  id: string;
  label: string;
  sublabel?: string;
  color?: string;
  icon?: string;
  tier?: string;
  file_count?: number;
  slug?: string;
  call_count?: number;
}

export interface DiagramEdge {
  from_: string;
  to: string;
  label?: string;
  rel_type?: string;
  weight?: number;
}

export interface DiagramData {
  nodes: DiagramNode[];
  edges: DiagramEdge[];
}

export interface DiagramsResponse {
  architecture: DiagramData;
  dependency_graph: DiagramData;
  module_relationships: DiagramData;
}

export interface SearchResultItem {
  type: "page" | "entity" | "module";
  id: string;
  title: string;
  snippet?: string;
  score?: number;
}

export interface SearchResults {
  query: string;
  total_results: number;
  results: SearchResultItem[];
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

// ─── HTTP helper ─────────────────────────────────────────────────────────────

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    // FastAPI wraps errors as { detail: { code, message } } or { detail: "string" }
    const detail = body?.detail ?? body;
    const err: ApiError =
      detail && typeof detail === "object" && detail.message
        ? detail
        : { code: "UNKNOWN", message: typeof detail === "string" ? detail : res.statusText };
    throw Object.assign(new Error(err.message), { status: res.status, ...err });
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ─── Repositories ─────────────────────────────────────────────────────────────

export const repositories = {
  create: (url: string, access_token?: string, branch?: string) =>
    request<Repository>("/repositories", {
      method: "POST",
      body: JSON.stringify({ url, access_token, branch }),
    }),

  list: (params?: { status?: Repository["status"]; page?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.page) qs.set("page", String(params.page));
    if (params?.limit) qs.set("limit", String(params.limit));
    return request<{ repositories: Repository[]; pagination: Pagination }>(
      `/repositories?${qs.toString()}`
    );
  },

  get: (id: string) => request<Repository>(`/repositories/${id}`),

  delete: (id: string) => request<void>(`/repositories/${id}`, { method: "DELETE" }),

  refresh: (id: string) =>
    request<UpdateEvent>(`/repositories/${id}/refresh`, { method: "POST" }),
};

// ─── Wikis ────────────────────────────────────────────────────────────────────

export const wikis = {
  get: (repositoryId: string) => request<Wiki>(`/wikis/${repositoryId}`),

  listPages: (repositoryId: string, pageType?: WikiPage["page_type"]) => {
    const qs = pageType ? `?page_type=${pageType}` : "";
    return request<WikiPage[]>(`/wikis/${repositoryId}/pages${qs}`);
  },

  getPage: (repositoryId: string, slug: string) =>
    request<WikiPage>(`/wikis/${repositoryId}/pages/${slug}`),

  listModules: (repositoryId: string) =>
    request<Module[]>(`/wikis/${repositoryId}/modules`),

  getModule: (repositoryId: string, slug: string) =>
    request<Module>(`/wikis/${repositoryId}/modules/${slug}`),

  getEntity: (repositoryId: string, qualifiedName: string) =>
    request<CodeEntity>(`/wikis/${repositoryId}/entities/${qualifiedName}`),

  getDiagrams: (repositoryId: string) =>
    request<DiagramsResponse>(`/wikis/${repositoryId}/diagrams`),
};

// ─── Chat ─────────────────────────────────────────────────────────────────────

export const chat = {
  createConversation: (repositoryId: string) =>
    request<ChatConversation>(`/chat/${repositoryId}/conversations`, { method: "POST" }),

  listConversations: (repositoryId: string) =>
    request<ChatConversation[]>(`/chat/${repositoryId}/conversations`),

  sendMessage: (conversationId: string, content: string) =>
    request<ChatMessage>(`/chat/conversations/${conversationId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
};

// ─── Search ───────────────────────────────────────────────────────────────────

export const search = {
  query: (
    repositoryId: string,
    q: string,
    type: "all" | "pages" | "entities" | "modules" = "all",
    limit = 20
  ) => {
    const qs = new URLSearchParams({ q, type, limit: String(limit) });
    return request<SearchResults>(`/search/${repositoryId}?${qs.toString()}`);
  },
};

// ─── SSE ──────────────────────────────────────────────────────────────────────

export function progressStreamUrl(repoId: string): string {
  return `${BASE_URL}/repositories/${repoId}/progress/stream`;
}

// ─── Unified namespace ────────────────────────────────────────────────────────

export const api = { repositories, wikis, chat, search };
