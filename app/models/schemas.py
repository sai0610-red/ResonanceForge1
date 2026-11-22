from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ReadinessScore(BaseModel):
    score: int = Field(..., ge=1, le=10)
    reason: str


class DiagnosisResult(BaseModel):
    access: ReadinessScore
    adapt: ReadinessScore
    adopt: ReadinessScore
    overall_readiness: Literal["Low", "Medium", "High"]
    top_gaps: List[str] = Field(..., min_length=3, max_length=5)
    summary: str


class AgentRole(BaseModel):
    name: str
    responsibility: str


class ArchitectureResult(BaseModel):
    recommended_agents: List[AgentRole]
    high_level_flow: List[str]
    rationale: str
    estimated_complexity: Literal["Low", "Medium", "High"]


class CodeGenerationResult(BaseModel):
    language: Literal["python"] = "python"
    framework: Literal["langgraph"] = "langgraph"
    code: str
    explanation: str


class CritiqueResult(BaseModel):
    strengths: List[str]
    weaknesses: List[str]
    risks: List[str]
    recommendations: List[str]
    final_verdict: Literal["Ready for pilot", "Needs work", "Not ready"]


class ChecklistAnswer(BaseModel):
    question_id: str
    value: int = Field(..., ge=1, le=5)


class AssessRequest(BaseModel):
    question: str
    industry: Optional[str] = None
    company_size: Optional[str] = None
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    primary_systems: Optional[str] = None
    constraints: Optional[str] = None
    success_metric: Optional[str] = None
    checklist: Optional[List[ChecklistAnswer]] = None
    # Optional: id returned by POST /api/documents. Grounds the Diagnostician
    # (when it uses the LLM) and the Architect in the customer's own documents.
    document_set_id: Optional[str] = None


class PilotPackageInfo(BaseModel):
    download_path: str
    filename: str
    what_breaks_first: List[str]


class ScaffoldCheck(BaseModel):
    """Static compile-check of generated code (ast.parse + compile, never exec)."""

    ok: bool
    error: Optional[str] = None
    lines: int = 0
    has_stategraph: bool = False
    has_compile: bool = False


class EvidenceDocument(BaseModel):
    label: str  # "D1"
    filename: str


class EvidencePassage(BaseModel):
    """A chunk that was retrieved and shown to an agent for this assessment."""

    ref: str  # "D1:C3"
    document: str
    chunk: int
    score: float
    text: str
    used_by: List[str] = Field(default_factory=list)
    cited: bool = False


class Evidence(BaseModel):
    document_set_id: str
    documents: List[EvidenceDocument] = Field(default_factory=list)
    passages: List[EvidencePassage] = Field(default_factory=list)
    # Citation markers the model produced that did not match a retrieved chunk.
    citations_dropped: int = 0


class ResonanceReport(BaseModel):
    user_question: str
    diagnosis: DiagnosisResult
    architecture: ArchitectureResult
    generated_code: CodeGenerationResult
    critique: CritiqueResult
    pilot: Optional[PilotPackageInfo] = None
    scaffold_check: Optional[ScaffoldCheck] = None
    evidence: Optional[Evidence] = None
