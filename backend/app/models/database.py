from __future__ import annotations

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey, Float
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime, timezone

Base = declarative_base()


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    relationship_type = Column(String(100), default="other")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    documents = relationship("Document", back_populates="profile", cascade="all, delete-orphan")
    analyses = relationship("AnalysisReport", back_populates="profile", cascade="all, delete-orphan")
    generated_skills = relationship("GeneratedSkill", back_populates="profile", cascade="all, delete-orphan")
    runtime_validation_results = relationship("RuntimeValidationResult", back_populates="profile", cascade="all, delete-orphan")
    skill_runtime_runs = relationship("SkillRuntimeRun", back_populates="profile", cascade="all, delete-orphan")
    skill_runtime_feedback = relationship("SkillRuntimeFeedback", back_populates="profile", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)
    content_type = Column(String(100), default="text/plain")
    char_count = Column(Integer, default=0)
    chunk_count = Column(Integer, default=0)
    parser = Column(String(50), default="builtin")
    parsed_text_path = Column(String(1000), nullable=True)
    original_file_path = Column(String(1000), nullable=True)
    parse_status = Column(String(50), default="success")
    parse_error = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    profile = relationship("Profile", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    char_count = Column(Integer, default=0)
    parser = Column(String(50), default="builtin")
    chroma_id = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    document = relationship("Document", back_populates="chunks")


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    portrait_report = Column(Text, default="")
    style_card = Column(Text, default="")
    evidence_json = Column(Text, default="")  # JSON: evidence_map per module
    total_chunks = Column(Integer, default=0)
    total_chars = Column(Integer, default=0)
    model_used = Column(String(100), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    profile = relationship("Profile", back_populates="analyses")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    retrieved_chunks = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class GeneratedSkill(Base):
    __tablename__ = "generated_skills"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    skill_type = Column(String(50), nullable=False)
    source_repo = Column(String(200), default="")
    source_path = Column(String(1000), default="")
    output_path = Column(String(1000), default="")
    generated_files_json = Column(Text, default="[]")
    status = Column(String(50), default="created")
    repo_imported = Column(Integer, default=0)
    spec_parsed = Column(Integer, default=0)
    compatible_skill_generated = Column(Integer, default=0)
    original_cli_invoked = Column(Integer, default=0)
    validation_status = Column(String(80), default="not_validated")
    validation_score = Column(Integer, default=0)
    validation_passed_checks_json = Column(Text, default="[]")
    validation_errors_json = Column(Text, default="[]")
    validation_warnings_json = Column(Text, default="[]")
    runtime_simulated = Column(Integer, default=0)
    actual_runtime_invoked = Column(Integer, default=0)
    runtime_test_output_path = Column(String(1000), default="")
    install_instructions_path = Column(String(1000), default="")
    last_validated_at = Column(DateTime, nullable=True)
    l5c_runtime_target = Column(String(80), default="")
    l5c_passed = Column(Integer, default=0)
    l5c_score = Column(Integer, default=0)
    l5c_result_id = Column(Integer, nullable=True)
    l5c_validated_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    profile = relationship("Profile", back_populates="generated_skills")
    runtime_validation_results = relationship("RuntimeValidationResult", back_populates="generated_skill", cascade="all, delete-orphan")
    skill_runtime_runs = relationship("SkillRuntimeRun", back_populates="generated_skill", cascade="all, delete-orphan")
    skill_runtime_feedback = relationship("SkillRuntimeFeedback", back_populates="generated_skill", cascade="all, delete-orphan")


class RuntimeValidationResult(Base):
    __tablename__ = "runtime_validation_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    generated_skill_id = Column(Integer, ForeignKey("generated_skills.id", ondelete="CASCADE"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    skill_type = Column(String(50), nullable=False)
    runtime_target = Column(String(80), default="generic_agent_skill")
    tester_note = Column(Text, default="")
    test_output_text = Column(Text, default="")
    score = Column(Integer, default=0)
    passed = Column(Integer, default=0)
    failed_cases_json = Column(Text, default="[]")
    warnings_json = Column(Text, default="[]")
    evidence_of_runtime = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    profile = relationship("Profile", back_populates="runtime_validation_results")
    generated_skill = relationship("GeneratedSkill", back_populates="runtime_validation_results")


class SkillRuntimeRun(Base):
    __tablename__ = "skill_runtime_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    generated_skill_id = Column(Integer, ForeignKey("generated_skills.id", ondelete="CASCADE"), nullable=False)
    skill_type = Column(String(50), nullable=False)
    runtime_mode = Column(String(80), default="evidence_check")
    user_prompt = Column(Text, default="")
    answer = Column(Text, default="")
    files_used_json = Column(Text, default="[]")
    evidence_used_json = Column(Text, default="[]")
    runtime_trace_json = Column(Text, default="{}")
    safety_check_json = Column(Text, default="{}")
    model_provider = Column(String(120), default="")
    status = Column(String(50), default="success")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    profile = relationship("Profile", back_populates="skill_runtime_runs")
    generated_skill = relationship("GeneratedSkill", back_populates="skill_runtime_runs")
    feedback = relationship("SkillRuntimeFeedback", back_populates="run", cascade="all, delete-orphan")


class SkillRuntimeFeedback(Base):
    __tablename__ = "skill_runtime_feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("skill_runtime_runs.id", ondelete="CASCADE"), nullable=False)
    profile_id = Column(Integer, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False)
    generated_skill_id = Column(Integer, ForeignKey("generated_skills.id", ondelete="CASCADE"), nullable=False)
    rating = Column(String(80), nullable=False)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    run = relationship("SkillRuntimeRun", back_populates="feedback")
    profile = relationship("Profile", back_populates="skill_runtime_feedback")
    generated_skill = relationship("GeneratedSkill", back_populates="skill_runtime_feedback")
