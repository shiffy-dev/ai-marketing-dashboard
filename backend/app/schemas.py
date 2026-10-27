from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]


class Hook(BaseModel):
    text: str
    technique: str


class Body(BaseModel):
    structure: str
    key_beats: list[str] = Field(default_factory=list)


class CTA(BaseModel):
    text: str
    type: str


class Driver(BaseModel):
    type: Literal["content", "distribution", "context"]
    claim: str
    evidence: str = Field(min_length=1)
    confidence: Confidence


class WhyTrending(BaseModel):
    summary: str
    drivers: list[Driver] = Field(min_length=1)
    unknowns: list[str] = Field(default_factory=list)
    takeaways: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    language: str
    hook: Hook
    body: Body
    cta: CTA
    why_trending: WhyTrending
    format_tags: list[str] = Field(default_factory=list)
    confidence: Confidence
