"""Deterministic regulation detection for onboarding requests.

Regulations are activated only by explicit language in the request (or by a
previously persisted human answer supplied by the caller). Data-column names
and observed values are deliberately not accepted as input to this detector;
they must never silently broaden the compliance scope.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


# Keep these canonical values aligned with the onboarding command vocabulary.
SUPPORTED_REGULATIONS = ("GDPR", "CCPA", "HIPAA", "SOX", "PCI")

_ALIASES: dict[str, tuple[str, ...]] = {
    "GDPR": (
        r"\bGDPR\b",
        r"\bGeneral\s+Data\s+Protection\s+Regulation\b",
    ),
    "CCPA": (
        r"\bCCPA\b",
        r"\bCalifornia\s+Consumer\s+Privacy\s+Act\b",
    ),
    "HIPAA": (
        r"\bHIPAA\b",
        r"\bHealth\s+Insurance\s+Portability\s+and\s+Accountability\s+Act\b",
    ),
    "SOX": (
        r"\bSOX\b",
        r"\bSarbanes[-\s]Oxley\b",
    ),
    "PCI": (
        r"\bPCI(?:\s*[-/]?\s*DSS)?\b",
        r"\bPayment\s+Card\s+Industry(?:\s+Data\s+Security\s+Standard)?\b",
    ),
}

_NEGATED_BEFORE = re.compile(
    r"(?:\bno\b|\bnot\b|\bwithout\b|\bexclude(?:d|s)?\b|\bskip\b|"
    r"\bomit(?:ted)?\b|\bavoid\b|\bdo\s+not\s+(?:apply|use|include)\b|"
    r"\bdon['’]t\s+(?:apply|use|include)\b)"
    r"(?:\W+\w+){0,3}\W*$",
    re.IGNORECASE,
)
_NEGATED_AFTER = re.compile(
    r"^\W*(?:(?:is|are|was|were)\W+)?"
    r"(?:not(?:\W+(?:required|needed|applicable|in[\s-]scope))?|"
    r"excluded|out\W+of\W+scope)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RegulationMatch:
    """One explicit regulation mention in the request."""

    regulation: str
    matched_text: str
    start: int
    end: int
    negated: bool = False


@dataclass(frozen=True)
class RegulationDetection:
    """The normalized result of scanning one onboarding request."""

    active: tuple[str, ...]
    matches: tuple[RegulationMatch, ...]
    excluded: tuple[str, ...]

    @property
    def has_explicit_selection(self) -> bool:
        return bool(self.active)

    def as_human_answer(self) -> list[str]:
        """Return the value suitable for ``human_answers.compliance``."""
        return list(self.active)


def _normalise_request(text: str) -> str:
    """Normalize punctuation without changing evidence offsets materially."""
    return text.replace("\N{NON-BREAKING HYPHEN}", "-").replace("\N{EN DASH}", "-")


def _is_negated(text: str, start: int, end: int) -> bool:
    prefix = text[max(0, start - 64) : start]
    suffix = text[end : min(len(text), end + 40)]
    return bool(_NEGATED_BEFORE.search(prefix) or _NEGATED_AFTER.search(suffix))


def detect_regulations(text: str) -> RegulationDetection:
    """Detect explicitly named regulations in free-form onboarding text.

    Results preserve first-mention order and remove duplicates. A regulation
    mentioned in an explicit negation, such as ``"GDPR is not required"``, is
    returned as excluded rather than activated.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    request = _normalise_request(text)
    matches: list[RegulationMatch] = []
    active: list[str] = []
    excluded: list[str] = []

    candidates: list[tuple[int, str, re.Match[str]]] = []
    for regulation, patterns in _ALIASES.items():
        for pattern in patterns:
            for match in re.finditer(pattern, request, re.IGNORECASE):
                candidates.append((match.start(), regulation, match))

    for _, regulation, match in sorted(candidates, key=lambda item: item[0]):
        negated = _is_negated(request, match.start(), match.end())
        evidence = RegulationMatch(
            regulation=regulation,
            matched_text=match.group(0),
            start=match.start(),
            end=match.end(),
            negated=negated,
        )
        matches.append(evidence)
        target = excluded if negated else active
        if regulation not in target:
            target.append(regulation)

    return RegulationDetection(
        active=tuple(active),
        matches=tuple(matches),
        excluded=tuple(excluded),
    )
