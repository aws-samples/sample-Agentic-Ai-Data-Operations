"""
Success Profiler: Identify successful patterns from trace logs.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from .schemas import (
    SuccessPattern,
    BestPractice,
    AGENT_TYPES,
)


class SuccessProfiler:
    """Extract and profile successful decision patterns."""

    def __init__(self, workloads_dir: Path = None):
        if workloads_dir is None:
            workloads_dir = Path.cwd() / 'workloads'
        self.workloads_dir = Path(workloads_dir)

    def profile_workload(self, workload_path: Path) -> List[SuccessPattern]:
        """Profile a single workload's successful runs."""
        trace_file = workload_path / 'logs' / 'trace_events.jsonl'

        if not trace_file.exists():
            return []

        patterns = []

        try:
            with open(trace_file, 'r') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())

                        if event.get('status') == 'completed' or event.get('status') == 'success':
                            agent_output = event.get('agent_output', {})

                            if not isinstance(agent_output, dict):
                                continue

                            blocking_issues = agent_output.get('blocking_issues', [])
                            if blocking_issues:
                                continue

                            decisions = agent_output.get('decisions', [])
                            for decision in decisions:
                                if not isinstance(decision, dict):
                                    continue

                                if decision.get('confidence') == 'high':
                                    pattern = self._extract_success_pattern(
                                        decision, event, workload_path
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

    def _extract_success_pattern(self, decision: Dict[str, Any], event: Dict[str, Any], workload_path: Path) -> Optional[SuccessPattern]:
        """Extract success pattern from a high-confidence decision."""
        decision_text = decision.get('decision', '')
        reasoning = decision.get('reasoning', '')

        if not decision_text:
            return None

        characteristics = self._get_workload_characteristics(workload_path)

        return SuccessPattern(
            workload=workload_path.name,
            agent_type=event.get('agent', 'unknown'),
            phase=event.get('phase', 0),
            decision=decision_text,
            reasoning=reasoning,
            confidence='high',
            timestamp=event.get('timestamp', ''),
            workload_characteristics=characteristics,
        )

    def _get_workload_characteristics(self, workload_path: Path) -> Dict[str, Any]:
        """Extract workload characteristics from config files."""
        characteristics = {}

        source_yaml = workload_path / 'config' / 'source.yaml'
        if source_yaml.exists():
            try:
                import yaml
                with open(source_yaml, 'r') as f:
                    source_config = yaml.safe_load(f)
                    characteristics['source_type'] = source_config.get('format', 'unknown')
                    characteristics['location'] = source_config.get('location', '').split('://')[0]
            except Exception:
                pass

        semantic_yaml = workload_path / 'config' / 'semantic.yaml'
        if semantic_yaml.exists():
            try:
                import yaml
                with open(semantic_yaml, 'r') as f:
                    semantic_config = yaml.safe_load(f)
                    characteristics['domain'] = semantic_config.get('domain', 'unknown')
                    characteristics['regulation'] = semantic_config.get('regulation', 'none')
            except Exception:
                pass

        return characteristics

    def extract_best_practices(self, patterns: List[SuccessPattern], min_confidence: float = 0.9, min_frequency: int = 5) -> List[BestPractice]:
        """Extract validated best practices."""
        groups = defaultdict(list)

        for pattern in patterns:
            key = (
                pattern.agent_type,
                pattern.phase,
                pattern.workload_characteristics.get('source_type', 'unknown'),
            )
            groups[key].append(pattern)

        best_practices = []

        for (agent_type, phase, source_type), group in groups.items():
            if len(group) < min_frequency:
                continue

            decision_counts = defaultdict(int)
            decision_examples = defaultdict(list)

            for pattern in group:
                decision_normalized = pattern.decision.lower().strip()
                decision_counts[decision_normalized] += 1
                decision_examples[decision_normalized].append(pattern.decision)

            top_decision = max(decision_counts.items(), key=lambda x: x[1])
            decision_text = top_decision[0]
            frequency = top_decision[1]

            success_rate = 1.0

            workload_types = list(set(
                p.workload_characteristics.get('source_type', 'unknown')
                for p in group
            ))

            context = self._generate_context(agent_type, phase, source_type, group)

            practice_id = BestPractice.generate_practice_id(decision_text, agent_type)

            practice = BestPractice(
                practice_id=practice_id,
                description=decision_text.capitalize(),
                agent_type=agent_type,
                phase=phase,
                workload_types=workload_types,
                frequency=frequency,
                success_rate=success_rate,
                context=context,
                example_decisions=decision_examples[decision_text][:3],
            )

            best_practices.append(practice)

        best_practices.sort(key=lambda p: p.frequency, reverse=True)

        return best_practices

    def _generate_context(self, agent_type: str, phase: int, source_type: str, patterns: List[SuccessPattern]) -> str:
        """Generate context for when to apply a best practice."""
        contexts = []

        if agent_type == AGENT_TYPES['METADATA']:
            contexts.append("When profiling data sources")
        elif agent_type == AGENT_TYPES['TRANSFORMATION']:
            contexts.append("When designing transformations")
        elif agent_type == AGENT_TYPES['QUALITY']:
            contexts.append("When setting quality rules")
        elif agent_type == AGENT_TYPES['DAG']:
            contexts.append("When orchestrating pipelines")

        if source_type and source_type != 'unknown':
            contexts.append(f"for {source_type.upper()} sources")

        if phase == 1:
            contexts.append("during discovery")
        elif phase == 3:
            contexts.append("during profiling")
        elif phase == 4:
            contexts.append("during pipeline generation")

        return " ".join(contexts).capitalize() + "."

    def profile_all_workloads(self) -> Tuple[List[SuccessPattern], List[BestPractice]]:
        """Profile all workloads."""
        all_patterns = []

        if not self.workloads_dir.exists():
            print(f"Workloads directory not found: {self.workloads_dir}")
            return [], []

        for workload_dir in self.workloads_dir.iterdir():
            if not workload_dir.is_dir():
                continue

            patterns = self.profile_workload(workload_dir)
            all_patterns.extend(patterns)

            if patterns:
                print(f"✓ {workload_dir.name}: {len(patterns)} success patterns")

        best_practices = self.extract_best_practices(all_patterns)

        return all_patterns, best_practices
