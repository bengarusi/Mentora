from dataclasses import dataclass, field


@dataclass
class ToolResult:
    """Structured result returned by any math tool."""

    success: bool
    tool_used: str  # e.g. "fraction_arithmetic", "sympy_algebra", "llm_fallback"
    canonical_answer: str | None = None  # normalised canonical form of the correct answer
    is_equivalent: bool | None = None    # None means "could not determine"
    steps_data: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
