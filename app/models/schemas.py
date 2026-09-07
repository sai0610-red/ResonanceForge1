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


class AssessRequest(BaseModel):
    question: str
    industry: Optional[str] = None
    company_size: Optional[str] = None


class ResonanceReport(BaseModel):
    user_question: str
    diagnosis: DiagnosisResult
    architecture: ArchitectureResult
    generated_code: CodeGenerationResult
    critique: CritiqueResult
