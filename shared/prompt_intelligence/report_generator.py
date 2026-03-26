"""
Report Generator: Generate human-readable analysis reports.
"""

from pathlib import Path
from typing import List
from datetime import datetime

from .schemas import (
    CrossWorkloadPattern,
    BestPractice,
    IMPACT_LEVELS,
)


class ReportGenerator:
    """Generate markdown reports from pattern analysis."""

    def generate_report(self, failure_patterns: List[CrossWorkloadPattern], best_practices: List[BestPractice], output_path: Path = None, top_n: int = None) -> str:
        """Generate comprehensive analysis report."""
        prioritized_failures = self.prioritize_recommendations(failure_patterns)

        if top_n:
            prioritized_failures = prioritized_failures[:top_n]
            best_practices = best_practices[:top_n]

        report_parts = [
            self._generate_header(len(failure_patterns), len(best_practices)),
            self._generate_executive_summary(prioritized_failures, best_practices),
            self._generate_failure_section(prioritized_failures),
            self._generate_best_practices_section(best_practices),
            self._generate_implementation_guide(),
            self._generate_footer(),
        ]

        report = "\n\n".join(report_parts)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(report)
            print(f"✓ Report saved to: {output_path}")

        return report

    def _generate_header(self, num_failures: int, num_practices: int) -> str:
        """Generate report header."""
        today = datetime.now().strftime('%Y-%m-%d')

        return f"""# Prompt Intelligence Report

**Generated**: {today}
**Failure Patterns Detected**: {num_failures}
**Best Practices Identified**: {num_practices}

---
"""

    def _generate_executive_summary(self, failures: List[CrossWorkloadPattern], practices: List[BestPractice]) -> str:
        """Generate executive summary."""
        blocking = sum(1 for p in failures if p.impact == IMPACT_LEVELS['BLOCKING'])
        degraded = sum(1 for p in failures if p.impact == IMPACT_LEVELS['DEGRADED'])
        minor = sum(1 for p in failures if p.impact == IMPACT_LEVELS['MINOR'])

        type_counts = {}
        for pattern in failures:
            type_counts[pattern.pattern_type] = type_counts.get(pattern.pattern_type, 0) + 1

        top_blockers = [p for p in failures if p.impact == IMPACT_LEVELS['BLOCKING']][:3]

        time_saved = self._estimate_time_savings(failures)

        lines = [
            "## Executive Summary",
            "",
            f"Analyzed trace logs across **{self._count_unique_workloads(failures)} workloads**.",
            "",
            "### Impact Distribution",
            f"- 🔴 **BLOCKING**: {blocking} patterns (test gate failures, pipeline stops)",
            f"- 🟡 **DEGRADED**: {degraded} patterns (quality/performance issues)",
            f"- 🟢 **MINOR**: {minor} patterns (cosmetic or one-off issues)",
            "",
            "### Pattern Types",
        ]

        for ptype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- **{ptype.replace('_', ' ').title()}**: {count} patterns")

        lines.extend([
            "",
            "### Top Blockers",
        ])

        if top_blockers:
            for i, pattern in enumerate(top_blockers, 1):
                lines.append(
                    f"{i}. **{pattern.signature}** "
                    f"({pattern.frequency} occurrences across {len(pattern.workloads_affected)} workloads)"
                )
        else:
            lines.append("None detected — excellent!")

        lines.extend([
            "",
            f"### Estimated Time Savings",
            f"Addressing high-priority patterns could save **{time_saved} hours** across future onboardings.",
            "",
        ])

        return "\n".join(lines)

    def _generate_failure_section(self, patterns: List[CrossWorkloadPattern]) -> str:
        """Generate failure patterns section."""
        if not patterns:
            return "## Failure Patterns\n\nNo failure patterns detected. System running smoothly!"

        blocking = [p for p in patterns if p.impact == IMPACT_LEVELS['BLOCKING']]
        degraded = [p for p in patterns if p.impact == IMPACT_LEVELS['DEGRADED']]
        minor = [p for p in patterns if p.impact == IMPACT_LEVELS['MINOR']]

        sections = []

        if blocking:
            sections.append(self._format_pattern_group("HIGH PRIORITY: Blocking Issues", blocking))

        if degraded:
            sections.append(self._format_pattern_group("MEDIUM PRIORITY: Degraded Performance", degraded))

        if minor:
            sections.append(self._format_pattern_group("LOW PRIORITY: Minor Issues", minor))

        return "## Failure Patterns\n\n" + "\n\n---\n\n".join(sections)

    def _format_pattern_group(self, title: str, patterns: List[CrossWorkloadPattern]) -> str:
        """Format a group of patterns."""
        lines = [
            f"### {title}",
            f"**Count**: {len(patterns)} patterns",
            "",
        ]

        for i, pattern in enumerate(patterns, 1):
            lines.extend([
                f"#### {i}. {pattern.signature}",
                pattern.to_markdown(),
                "",
            ])

        return "\n".join(lines)

    def _generate_best_practices_section(self, practices: List[BestPractice]) -> str:
        """Generate best practices section."""
        if not practices:
            return "## Best Practices\n\nNot enough data to identify best practices yet. Keep onboarding workloads!"

        lines = [
            "## Best Practices",
            f"**Count**: {len(practices)} validated practices",
            "",
            "These decision patterns consistently lead to successful outcomes:",
            "",
        ]

        for i, practice in enumerate(practices, 1):
            lines.extend([
                f"### {i}. {practice.description}",
                practice.to_markdown(),
                "",
            ])

        return "\n".join(lines)

    def _generate_implementation_guide(self) -> str:
        """Generate implementation guide."""
        return """## Implementation Guide

### How to Apply These Findings

#### 1. Review High-Priority Patterns
Start with BLOCKING issues. These cause test gate failures and stop pipelines.

#### 2. Update Prompts
For each pattern with a `prompt_patch`:
1. Open the specified prompt file
2. Navigate to the specified section
3. Add the suggested patch text
4. Test with a new workload to verify the fix works

#### 3. Update Shared Utilities
Some patterns require code changes:
- PII false positives → Update `shared/utils/pii_detection_and_tagging.py`
- Schema validation → Update `shared/utils/schema_utils.py`
- Quality rules → Update `shared/utils/quality_checks.py`

#### 4. Document in CLAUDE.md
Once validated, add successful patterns to `CLAUDE.md`.

#### 5. Track Effectiveness
After applying fixes:
1. Run new onboardings
2. Check if the pattern stops appearing in trace logs
3. Update pattern confidence in future reports
"""

    def _generate_footer(self) -> str:
        """Generate report footer."""
        return """---

## Next Steps

1. **Immediate**: Address all BLOCKING patterns
2. **Short-term**: Fix DEGRADED patterns
3. **Long-term**: Incorporate best practices into standard workflows

---

*Report generated by Prompt Intelligence MVP*
"""

    def prioritize_recommendations(self, patterns: List[CrossWorkloadPattern]) -> List[CrossWorkloadPattern]:
        """Prioritize patterns by impact × confidence × frequency."""
        def priority_score(pattern: CrossWorkloadPattern) -> float:
            impact_weights = {
                IMPACT_LEVELS['BLOCKING']: 3.0,
                IMPACT_LEVELS['DEGRADED']: 2.0,
                IMPACT_LEVELS['MINOR']: 1.0,
            }
            impact_score = impact_weights.get(pattern.impact, 1.0)
            confidence_score = pattern.confidence
            frequency_score = min(pattern.frequency / 20.0, 1.0)
            return impact_score * confidence_score * frequency_score

        sorted_patterns = sorted(patterns, key=priority_score, reverse=True)
        return sorted_patterns

    def _estimate_time_savings(self, patterns: List[CrossWorkloadPattern]) -> str:
        """Estimate time savings from fixing patterns."""
        blocking_patterns = [p for p in patterns if p.impact == IMPACT_LEVELS['BLOCKING']]
        degraded_patterns = [p for p in patterns if p.impact == IMPACT_LEVELS['DEGRADED']]
        minor_patterns = [p for p in patterns if p.impact == IMPACT_LEVELS['MINOR']]

        blocking_hours = sum(p.frequency * 2 for p in blocking_patterns)
        degraded_hours = sum(p.frequency * 1 for p in degraded_patterns)
        minor_hours = sum(p.frequency * 0.5 for p in minor_patterns)

        total_hours = blocking_hours + degraded_hours + minor_hours
        estimated_savings = total_hours * 0.5

        if estimated_savings < 5:
            return "2-5"
        elif estimated_savings < 15:
            return "10-15"
        elif estimated_savings < 30:
            return "20-30"
        else:
            return "30+"

    def _count_unique_workloads(self, patterns: List[CrossWorkloadPattern]) -> int:
        """Count unique workloads across all patterns."""
        workloads = set()
        for pattern in patterns:
            workloads.update(pattern.workloads_affected)
        return len(workloads)
