"""Pydantic models shared across the pipeline. Structures = contracts between agents."""

from typing import Literal
from pydantic import BaseModel, Field


class Research(BaseModel):
    """Output of the Researcher Agent."""
    topic: str = ""
    angles: list[str] = Field(default_factory=list, description="Distinct content angles/hook ideas")
    key_facts: list[str] = Field(default_factory=list, description="Concrete facts, terms, or patterns worth citing")
    audience: str = Field(default="general professional audience", description="Who this content is for")


class Post(BaseModel):
    """One draft LinkedIn post."""
    style: str = Field(default="untitled", description="Short style label, e.g. 'story', 'listicle', 'hot-take'")
    text: str = Field(default="", description="The full post text")


class Draft(BaseModel):
    """Output of the Writer Agent."""
    posts: list[Post] = Field(default_factory=list)


class Review(BaseModel):
    """Output of the Editor Agent for one post."""
    verdict: Literal["publish", "reject"] = "reject"
    feedback: str = Field(default="", description="Specific, actionable feedback if rejected")


class FactCheck(BaseModel):
    """Output of the Fact-Checker Agent for one post."""
    verdict: Literal["publish", "reject"] = "reject"
    unsupported_claims: list[str] = Field(default_factory=list, description="Claims with no support in the research")
    note: str = Field(default="", description="Short note; explain if rejected")


class FinalPost(BaseModel):
    """A post at the end of the pipeline, regardless of outcome."""
    style: str = "untitled"
    text: str = ""
    feedback: str = Field(default="", description="Last rejection feedback, if any")
    editor_rounds: int = 0
    factcheck_rounds: int = 0
    pipeline_result: Literal["published", "failed_editor", "failed_factcheck"]


class PipelineResult(BaseModel):
    """Everything the pipeline produced."""
    topic: str = ""
    posts: list[FinalPost] = Field(default_factory=list)
