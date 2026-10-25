"""
Failure Analyzer: Extract failure patterns from trace logs.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .patch_registry import PromptEvolver
from collections import defaultdict

from .schemas import (
    FailurePattern,
    CrossWorkloadPattern,
    PATTERN_TYPES,
    IMPACT_LEVELS,
)


class FailureAnalyzer:
    """Extract and analyze failure patterns from trace logs."""

    def __init__(self, workloads_dir: Path = None):
        if workloads_dir is None:
            workloads_dir = Path.cwd() / 'workloads'
        self.workloads_dir = Path(workloads_dir)

    def analyze_workload(self, workload_path: Path) -> List[FailurePattern]:
        """Analyze a single workload's trace logs for failures."""
        trace_file = workload_path / 'logs' / 'trace_events.jsonl'

        if not trace_file.exists():
            return []

        patterns = []

        try:
            with open(trace_file, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())

                        # Look for failure events
                        if event.get('status') == 'failed' or event.get('event_type') == 'error':
                            pattern = self._extract_failure_pattern(event, workload_path.name)
                            if pattern:
                                patterns.append(pattern)

                        # Check agent_output for blocking_issues
                        agent_output = event.get('agent_output', {})
                        if isinstance(agent_output, dict):
                            blocking_issues = agent_output.get('blocking_issues', [])
                            if blocking_issues:
                                for issue in blocking_issues:
                                    pattern = self._extract_failure_from_issue(
                                        issue, event, workload_path.name
                                    )
                                    if pattern:
                                        patterns.append(pattern)
                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        continue

        except Exception as e:
            print(f"Error reading trace file {trace_file}: {e}")
            return []

        return patterns

    def _extract_failure_pattern(self, event: Dict[str, Any], workload: str) -> Optional[FailurePattern]:
        """Extract failure pattern from a trace event."""
        error_message = event.get('error', event.get('message', ''))
        if not error_message:
            return None

        signature = self.extract_signature(error_message)
        error_type = self._classify_error_type(error_message)

        agent_type = event.get('agent', 'unknown')
        phase = event.get('phase', 0)

        agent_output = event.get('agent_output', {})
        decisions = agent_output.get('decisions', []) if isinstance(agent_output, dict) else []
        low_confidence_decisions = [
            d for d in decisions
            if isinstance(d, dict) and d.get('confidence') in ['low', 'medium']
        ]

        context = {
            'event_type': event.get('event_type'),
            'operation': event.get('operation'),
            'run_id': event.get('run_id'),
        }

        return FailurePattern(
            workload=workload,
            signature=signature,
            error_type=error_type,
            error_message=error_message,
            agent_type=agent_type,
            phase=phase,
            timestamp=event.get('timestamp', ''),
            low_confidence_decisions=low_confidence_decisions,
            context=context,
        )

    def _extract_failure_from_issue(self, issue: Dict[str, Any], event: Dict[str, Any], workload: str) -> Optional[FailurePattern]:
        """Extract failure pattern from a blocking_issue."""
        error_message = issue.get('issue', '')
        if not error_message:
            return None

        signature = self.extract_signature(error_message)
        error_type = self._classify_error_type(error_message)

        agent_output = event.get('agent_output', {})
        decisions = agent_output.get('decisions', []) if isinstance(agent_output, dict) else []
        low_confidence_decisions = [
            d for d in decisions
            if isinstance(d, dict) and d.get('confidence') in ['low', 'medium']
        ]

        context = {
            'severity': issue.get('severity'),
            'category': issue.get('category'),
            'run_id': event.get('run_id'),
        }

        return FailurePattern(
            workload=workload,
            signature=signature,
            error_type=error_type,
            error_message=error_message,
            agent_type=event.get('agent', 'unknown'),
            phase=event.get('phase', 0),
            timestamp=event.get('timestamp', ''),
            low_confidence_decisions=low_confidence_decisions,
            context=context,
        )

    def extract_signature(self, error: str) -> str:
        """Extract normalized error signature."""
        if isinstance(error, dict):
            error = error.get('issue', error.get('error', str(error)))

        error = str(error).strip()

        # KeyError patterns
        if 'KeyError' in error:
            match = re.search(r"KeyError:\s*['\"]([^'\"]+)['\"]", error)
            if match:
                return f"KeyError: '{match.group(1)}'"
            return "KeyError"

        # AssertionError patterns
        if 'AssertionError' in error:
            match = re.search(r"AssertionError:\s*(.+?)(?:\n|$)", error)
            if match:
                msg = match.group(1).strip()
                msg = re.sub(r'\d+\.\d+', 'X.XX', msg)
                msg = re.sub(r'\d+', 'N', msg)
                msg = re.sub(r'/[^\s]+', '/path/', msg)
                return f"AssertionError: {msg}"
            return "AssertionError"

        # PII false positive patterns
        if 'flagged as PII' in error or 'PII detection' in error:
            match = re.search(r"(\w+)\s+flagged as PII", error)
            if match:
                return f"PII false positive: {match.group(1)}"
            return "PII false positive"

        # Quality threshold patterns
        if 'quality score' in error.lower() or 'threshold' in error.lower():
            match = re.search(r"(completeness|accuracy|uniqueness|validity|consistency)", error, re.IGNORECASE)
            if match:
                return f"Quality threshold: {match.group(1).lower()}"
            return "Quality threshold exceeded"

        # Generic fallback
        normalized = re.sub(r'\d+', 'N', error[:100])
        normalized = re.sub(r'/[^\s]+', '/path/', normalized)
        return normalized

    def _classify_error_type(self, error: str) -> str:
        """Classify error into a category."""
        error_lower = error.lower()

        if 'keyerror' in error_lower:
            return 'KeyError'
        elif 'assertionerror' in error_lower:
            return 'AssertionError'
        elif 'validation' in error_lower:
            return 'ValidationError'
        elif 'pii' in error_lower:
            return 'PIIError'
        elif 'quality' in error_lower or 'threshold' in error_lower:
            return 'QualityError'
        elif 'schema' in error_lower:
            return 'SchemaError'
        else:
            return 'UnknownError'

    def aggregate_cross_workload(self, patterns: List[FailurePattern]) -> List[CrossWorkloadPattern]:
        """Aggregate failure patterns across workloads."""
        groups = defaultdict(list)

        for pattern in patterns:
            key = (pattern.signature, pattern.agent_type, pattern.phase)
            groups[key].append(pattern)

        cross_patterns = []

        for (signature, agent_type, phase), group in groups.items():
            workloads_affected = list(set(p.workload for p in group))
            frequency = len(group)

            pattern_type = self._classify_pattern_type(signature)
            impact = self._determine_impact(group)
            confidence = self._calculate_confidence(frequency, len(workloads_affected))
            recommendation = self._generate_recommendation(signature, pattern_type, agent_type, phase)
            root_cause = self._analyze_root_cause(signature, pattern_type, group)
            prompt_section = f"Phase {phase}: {agent_type.title()} Agent"
            prompt_patch = self._generate_prompt_patch(signature, pattern_type, recommendation)

            examples = [
                {
                    'workload': p.workload,
                    'error_message': p.error_message,
                    'timestamp': p.timestamp,
                }
                for p in group[:5]
            ]

            pattern_id = CrossWorkloadPattern.generate_pattern_id(signature, agent_type, phase)

            cross_pattern = CrossWorkloadPattern(
                pattern_id=pattern_id,
                pattern_type=pattern_type,
                signature=signature,
                frequency=frequency,
                workloads_affected=workloads_affected,
                agent_type=agent_type,
                phase=phase,
                recommendation=recommendation,
                confidence=confidence,
                impact=impact,
                root_cause=root_cause,
                prompt_section=prompt_section,
                prompt_patch=prompt_patch,
                examples=examples,
            )

            cross_patterns.append(cross_pattern)

        cross_patterns.sort(key=lambda p: (p.frequency, p.confidence), reverse=True)

        return cross_patterns

    def _classify_pattern_type(self, signature: str) -> str:
        """Classify signature into pattern type."""
        sig_lower = signature.lower()

        if 'keyerror' in sig_lower or 'missing column' in sig_lower or 'schema' in sig_lower:
            return PATTERN_TYPES['SCHEMA_ERROR']
        elif 'pii' in sig_lower:
            return PATTERN_TYPES['PII_FALSE_POSITIVE']
        elif 'quality' in sig_lower or 'threshold' in sig_lower:
            return PATTERN_TYPES['QUALITY_THRESHOLD']
        else:
            return 'unknown'

    def _determine_impact(self, patterns: List[FailurePattern]) -> str:
        """Determine impact level."""
        for pattern in patterns:
            severity = pattern.context.get('severity', '').lower()
            if severity == 'critical' or 'test gate' in pattern.error_message.lower():
                return IMPACT_LEVELS['BLOCKING']

        if len(set(p.workload for p in patterns)) >= 3:
            return IMPACT_LEVELS['DEGRADED']

        return IMPACT_LEVELS['MINOR']

    def _calculate_confidence(self, frequency: int, num_workloads: int) -> float:
        """Calculate confidence score."""
        freq_score = min(frequency / 10.0, 0.6)
        workload_score = min(num_workloads / 5.0, 0.4)
        return min(freq_score + workload_score, 1.0)

    def _generate_recommendation(self, signature: str, pattern_type: str, agent_type: str, phase: int) -> str:
        """Generate actionable recommendation."""
        if pattern_type == PATTERN_TYPES['SCHEMA_ERROR']:
            if 'primary_key' in signature.lower():
                return "For CSV sources: ALWAYS ask 'What is the primary key?' before profiling. If composite key, list ALL columns."
            elif 'missing column' in signature.lower():
                return "Validate expected columns exist in source before transformation. Add explicit column check in profiling phase."
            else:
                return "Compare inferred schema against expected schema from config/semantic.yaml before pipeline execution."
        elif pattern_type == PATTERN_TYPES['PII_FALSE_POSITIVE']:
            return "Add to PII detection exclusion list. Review name-based detection rules for business entities."
        elif pattern_type == PATTERN_TYPES['QUALITY_THRESHOLD']:
            return "Review quality threshold. Consider nullable columns and expected null patterns. Adjust threshold or exclude expected-null columns."
        else:
            return f"Review {agent_type} agent logic for {signature}. Add validation or adjust configuration in Phase {phase}."

    def _analyze_root_cause(self, signature: str, pattern_type: str, patterns: List[FailurePattern]) -> str:
        """Analyze root cause."""
        if pattern_type == PATTERN_TYPES['SCHEMA_ERROR']:
            if 'primary_key' in signature.lower():
                return "CSV sources lack explicit PK column. Agent infers from uniqueness but often wrong. User input missing during discovery phase."
            else:
                return "Schema mismatch between source and expected structure."
        elif pattern_type == PATTERN_TYPES['PII_FALSE_POSITIVE']:
            return "Name-based PII detection flagging non-PII columns. Need business-context aware exclusion rules."
        elif pattern_type == PATTERN_TYPES['QUALITY_THRESHOLD']:
            return "Quality threshold set too strict for data characteristics. Need workload-specific tuning."
        else:
            return f"Recurring pattern across {len(patterns)} occurrences. Investigation needed."

    def _generate_prompt_patch(self, signature: str, pattern_type: str, recommendation: str) -> Optional[str]:
        """Generate prompt patch."""
        if pattern_type == PATTERN_TYPES['SCHEMA_ERROR'] and 'primary_key' in signature.lower():
            return """⚠️ **CRITICAL: Primary Key Detection**

For CSV sources without explicit PK column:
1. ALWAYS ask user: "What is the primary key for this data?"
2. If composite key: List ALL columns in order
3. If no natural PK: Confirm use of row_hash
4. NEVER infer PK from uniqueness alone

Add this question to discovery checklist BEFORE profiling."""
        return None

    def analyze_all_workloads(self) -> Tuple[List[FailurePattern], List[CrossWorkloadPattern]]:
        """Analyze all workloads."""
        all_patterns = []

        if not self.workloads_dir.exists():
            print(f"Workloads directory not found: {self.workloads_dir}")
            return [], []

        for workload_dir in self.workloads_dir.iterdir():
            if not workload_dir.is_dir():
                continue

            patterns = self.analyze_workload(workload_dir)
            all_patterns.extend(patterns)

            if patterns:
                print(f"✓ {workload_dir.name}: {len(patterns)} patterns")

        cross_patterns = self.aggregate_cross_workload(all_patterns)

        return all_patterns, cross_patterns

    def analyze_and_evolve(
        self,
        prompt_evolver: "PromptEvolver",
        auto_graft: bool = True,
        min_confidence: float = 0.60,
    ) -> Dict[str, Any]:
        """
        Full self-healing cycle: analyze -> filter -> harvest -> auto-graft.

        This is the method called by the nightly Lambda and CLI.
        """
        failures, cross_patterns = self.analyze_all_workloads()
        patchable = [
            p for p in cross_patterns
            if p.prompt_patch and p.confidence >= min_confidence
        ]
        result = prompt_evolver.harvest_insights(patchable, auto_graft=auto_graft)
        workload_names = set()
        for f in failures:
            workload_names.add(f.workload)
        return {
            "workloads_analyzed": len(workload_names),
            "patterns_found": len(cross_patterns),
            **result,
        }
