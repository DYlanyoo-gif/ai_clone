from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Profile ──
class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    relationship_type: str = Field(default="other", max_length=100)


class ProfileResponse(BaseModel):
    id: int
    name: str
    description: str
    relationship_type: str
    created_at: datetime
    updated_at: datetime
    document_count: int = 0
    chunk_count: int = 0
    has_analysis: bool = False

    model_config = {"from_attributes": True}


class ProfileDetail(ProfileResponse):
    total_chars: int = 0
    latest_portrait: Optional[str] = None
    latest_style_card: Optional[str] = None
    evidence_json: Optional[str] = None
    analysis_quality: Optional[dict] = None


# ── Document ──
class DocumentResponse(BaseModel):
    id: int
    profile_id: int
    filename: str
    file_type: str
    content_type: str
    char_count: int
    chunk_count: int
    parser: Optional[str] = None
    parse_status: Optional[str] = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


# ── Analysis ──
class AnalysisResponse(BaseModel):
    id: int
    profile_id: int
    portrait_report: str
    style_card: str
    evidence_json: Optional[str] = None
    total_chunks: int
    total_chars: int
    model_used: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfilePipelineOptions(BaseModel):
    run_analysis: bool = True
    generate_nuwa_skill: bool = True
    generate_colleague_skill: bool = True
    validate_skills: bool = True
    prepare_website_runtime: bool = True
    run_dry_run: bool = False
    generate_runtime_testcases: bool = False


class ProfilePipelineStepStatus(BaseModel):
    status: str = "pending"
    detail: str = ""
    skill_id: Optional[int] = None
    analysis_id: Optional[int] = None
    model_used: Optional[str] = None


class ProfilePipelineResponse(BaseModel):
    profile_id: int
    pipeline_status: str = "pending"
    analysis_ready: bool = False
    evidence_ready: bool = False
    skills_ready: bool = False
    runtime_ready: bool = False
    nuwa_skill_id: Optional[int] = None
    colleague_skill_id: Optional[int] = None
    analysis_status: ProfilePipelineStepStatus = Field(default_factory=ProfilePipelineStepStatus)
    evidence_status: ProfilePipelineStepStatus = Field(default_factory=ProfilePipelineStepStatus)
    nuwa_skill_status: ProfilePipelineStepStatus = Field(default_factory=ProfilePipelineStepStatus)
    colleague_skill_status: ProfilePipelineStepStatus = Field(default_factory=ProfilePipelineStepStatus)
    validation_status: ProfilePipelineStepStatus = Field(default_factory=ProfilePipelineStepStatus)
    website_runtime_ready: bool = False
    warnings: list[str] = []
    errors: list[str] = []
    next_actions: list[str] = []


class EvidenceClaim(BaseModel):
    claim: str
    evidence: list[dict] = []
    confidence_score: int = 0
    data_gap: Optional[str] = None
    contradiction: Optional[str] = None


class EvidenceModule(BaseModel):
    module_name: str
    claims: list[EvidenceClaim] = []
    data_sufficient: bool = True


class AnalysisQuality(BaseModel):
    total_chars: int = 0
    document_count: int = 0
    chunk_count: int = 0
    evidence_coverage: float = 0.0
    avg_confidence: float = 0.0
    diversity_score: float = 0.0
    has_chat_corpus: bool = False
    has_long_text: bool = False
    has_multi_emotion: bool = False
    suitability_level: str = "rough"
    suitability_label: str = "粗略画像"


# ── Chat ──
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    mode: str = Field(
        default="daily_chat",
        pattern=r"^(daily_chat|deep_analysis|comfort|advice|style_clone|communication_strategy)$",
    )


class ChatResponse(BaseModel):
    reply: str
    profile_name: str
    retrieved_count: int = 0
    model_used: str = ""
    retrieval_method: str = "keyword"
    retrieved_chunks: list[dict] = []


class ChatMessageResponse(BaseModel):
    id: int
    profile_id: int
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Generic ──
class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None


class MineruStatusResponse(BaseModel):
    installed: bool
    command: Optional[str] = None
    version_or_help: Optional[str] = None
    error: Optional[str] = None
    enabled: bool
    backend: str = "pipeline"
    method: str = "auto"
    lang: str = "ch"
    formula: bool = True
    table: bool = True
    image_analysis: bool = False
    timeout_seconds: int = 300


class Mem0StatusResponse(BaseModel):
    installed: bool
    enabled: bool
    available: bool = False
    provider: str = "local"
    error: Optional[str] = None
    detail: str = ""


class VectorStatusResponse(BaseModel):
    installed: bool
    enabled: bool
    available: bool = False
    provider: str = "qdrant"
    embedding_model: str = ""
    error: Optional[str] = None
    detail: str = ""
    collection: Optional[str] = None
    points_count: int = 0
    indexed: bool = False


class VectorRebuildResponse(BaseModel):
    indexed: int = 0
    error: Optional[str] = None
    detail: str = ""


class VectorSearchResponse(BaseModel):
    query: str
    retrieval_method: str = "keyword"
    results: list[dict] = []
    total: int = 0


class SkillIntegrationStatusResponse(BaseModel):
    name: str
    installed: bool = False
    available: bool = False
    source_repo: str = ""
    source_path: str = ""
    error: Optional[str] = None
    detail: str = ""
    level: str = "L0"
    level_label: str = "提及"


class SkillSpecResponse(BaseModel):
    name: str
    source_repo: str = ""
    source_path: str = ""
    project_name: str = ""
    description: str = ""
    skill_purpose: list[str] = []
    input_requirements: list[str] = []
    workflow: list[str] = []
    output_contract: list[str] = []
    runtime_hosts: list[str] = []
    limitations: list[str] = []
    raw_files_read: list[str] = []


class GeneratedSkillResponse(BaseModel):
    id: int
    profile_id: int
    skill_type: str
    source_repo: str
    source_path: str
    output_path: str
    generated_files: list[str] = []
    status: str
    repo_imported: bool = False
    spec_parsed: bool = False
    compatible_skill_generated: bool = False
    original_cli_invoked: bool = False
    validation_status: str = "not_validated"
    validation_score: int = 0
    validation_passed_checks: list[str] = []
    validation_errors: list[str] = []
    validation_warnings: list[str] = []
    runtime_simulated: bool = False
    actual_runtime_invoked: bool = False
    runtime_test_output_path: str = ""
    install_instructions_path: str = ""
    last_validated_at: Optional[datetime] = None
    l5c_runtime_target: str = ""
    l5c_passed: bool = False
    l5c_score: int = 0
    l5c_result_id: Optional[int] = None
    l5c_validated_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class SkillGenerateResponse(BaseModel):
    generated: bool = False
    skill: Optional[GeneratedSkillResponse] = None
    detail: str = ""
    error: Optional[str] = None


class SkillValidationResponse(BaseModel):
    validation_score: int = 0
    runtime_ready: bool = False
    level: str = "L4-compatible-generated"
    passed_checks: list[str] = []
    warnings: list[str] = []
    errors: list[str] = []
    runtime_simulated: bool = False
    actual_runtime_invoked: bool = False
    install_instructions_path: str = ""
    simulated_output: Optional[str] = None
    used_files: list[str] = []
    error: Optional[str] = None


class SkillDryRunRequest(BaseModel):
    test_prompt: str = Field(default="请说明你会如何使用 evidence_policy，并指出资料不足时应该如何回答。", max_length=2000)


class RuntimeTestCaseRequest(BaseModel):
    runtime_target: str = Field(default="codex", max_length=80)


class RuntimeTestCasesResponse(BaseModel):
    runtime_target: str = "codex"
    markdown_path: str = ""
    json_path: str = ""
    test_cases: list[dict] = []
    warnings: list[str] = []


class RuntimeResultSubmitRequest(BaseModel):
    runtime_target: str = Field(default="codex", max_length=80)
    tester_note: str = Field(default="", max_length=5000)
    test_output_text: str = Field(..., min_length=1, max_length=60000)
    evidence_of_runtime: str = Field(default="", max_length=5000)


class RuntimeResultResponse(BaseModel):
    id: int
    generated_skill_id: int
    profile_id: int
    skill_type: str
    runtime_target: str
    tester_note: str = ""
    test_output_text: str = ""
    score: int = 0
    passed: bool = False
    failed_cases: list[str] = []
    warnings: list[str] = []
    evidence_of_runtime: str = ""
    created_at: datetime


class RuntimeEvaluationResponse(BaseModel):
    result_id: Optional[int] = None
    score: int = 0
    passed: bool = False
    failed_cases: list[str] = []
    warnings: list[str] = []
    recommended_fix: str = ""
    can_mark_l5c: bool = False
    judgeable_cases: int = 0
    safety_boundary_passed: bool = False
    evidence_policy_passed: bool = False


class SkillWebsiteRunRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1, max_length=8000)
    runtime_mode: str = Field(
        default="evidence_check",
        pattern=r"^(nuwa_thinking|colleague_interaction|compare|evidence_check|uncertainty_check)$",
    )


class SkillRuntimeRunResponse(BaseModel):
    id: Optional[int] = None
    profile_id: int
    generated_skill_id: int
    skill_type: str
    runtime_mode: str
    user_prompt: str
    answer: str = ""
    model_provider: str = ""
    files_used: list[str] = []
    evidence_used: list[dict] = []
    uncertainty_notes: list[str] = []
    safety_check: dict = {}
    runtime_trace: dict = {}
    status: str = "success"
    error: Optional[str] = None
    created_at: datetime


class SkillCompareRunRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1, max_length=8000)
    nuwa_skill_id: int
    colleague_skill_id: int


class SkillCompareRunResponse(BaseModel):
    nuwa_result: SkillRuntimeRunResponse
    colleague_result: SkillRuntimeRunResponse
    comparison_summary: str = ""
    difference_table: list[dict] = []
    recommendation: str = ""


class SkillRuntimeFeedbackRequest(BaseModel):
    rating: str = Field(
        ...,
        pattern=r"^(good|inaccurate|unsafe|not_like_person|missing_evidence)$",
    )
    note: str = Field(default="", max_length=5000)


class SkillRuntimeFeedbackResponse(BaseModel):
    id: int
    run_id: int
    profile_id: int
    generated_skill_id: int
    rating: str
    note: str = ""
    correction_history_appended: bool = False
    created_at: datetime


class MemoryRebuildResponse(BaseModel):
    stored: int
    error: Optional[str] = None


class MemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
