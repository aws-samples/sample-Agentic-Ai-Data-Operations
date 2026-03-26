"""
CLI: Command-line interface for Prompt Intelligence.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Prompt Intelligence: Self-healing prompt analysis'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze workload traces')
    analyze_parser.add_argument('--workload', type=str, help='Analyze specific workload')
    analyze_parser.add_argument('--all', action='store_true', help='Analyze all workloads')
    analyze_parser.add_argument('--output', type=str, help='Output file path')
    analyze_parser.add_argument('--top', type=int, help='Show only top N patterns')
    analyze_parser.add_argument('--workloads-dir', type=str, default='workloads')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'analyze':
        run_analyze(args)


def run_analyze(args):
    """Run analysis command."""
    from .failure_analyzer import FailureAnalyzer
    from .success_profiler import SuccessProfiler
    from .report_generator import ReportGenerator

    workloads_dir = Path(args.workloads_dir)

    if not workloads_dir.exists():
        print(f"❌ Workloads directory not found: {workloads_dir}")
        sys.exit(1)

    print("=" * 60)
    print("Prompt Intelligence Analysis")
    print("=" * 60)
    print()

    failure_analyzer = FailureAnalyzer(workloads_dir=workloads_dir)
    success_profiler = SuccessProfiler(workloads_dir=workloads_dir)
    report_generator = ReportGenerator()

    if args.all:
        print("Analyzing all workloads...")
        print()
        all_failure_patterns, cross_patterns = failure_analyzer.analyze_all_workloads()
        all_success_patterns, best_practices = success_profiler.profile_all_workloads()
    elif args.workload:
        workload_path = workloads_dir / args.workload
        if not workload_path.exists():
            print(f"❌ Workload not found: {args.workload}")
            sys.exit(1)

        print(f"Analyzing workload: {args.workload}")
        print()

        failure_patterns = failure_analyzer.analyze_workload(workload_path)
        success_patterns = success_profiler.profile_workload(workload_path)

        cross_patterns = failure_analyzer.aggregate_cross_workload(failure_patterns)
        best_practices = success_profiler.extract_best_practices(success_patterns, min_frequency=1)
    else:
        print("❌ Must specify --all or --workload <name>")
        sys.exit(1)

    print()
    print("-" * 60)
    print("Analysis Complete")
    print("-" * 60)
    print()

    print(f"✓ Found {len(cross_patterns)} cross-workload failure patterns")
    print(f"✓ Found {len(best_practices)} validated best practices")
    print()

    blocking = sum(1 for p in cross_patterns if p.impact == 'blocking')
    degraded = sum(1 for p in cross_patterns if p.impact == 'degraded')
    minor = sum(1 for p in cross_patterns if p.impact == 'minor')

    print("Impact Distribution:")
    print(f"  🔴 BLOCKING:  {blocking} patterns")
    print(f"  🟡 DEGRADED:  {degraded} patterns")
    print(f"  🟢 MINOR:     {minor} patterns")
    print()

    if cross_patterns:
        print("Top Failure Patterns:")
        for i, pattern in enumerate(cross_patterns[:5], 1):
            confidence_bar = "█" * int(pattern.confidence * 10)
            print(f"  {i}. {pattern.signature}")
            print(f"     Frequency: {pattern.frequency}, "
                  f"Workloads: {len(pattern.workloads_affected)}, "
                  f"Confidence: {confidence_bar} {pattern.confidence:.2f}")
        print()

    output_path = args.output
    if not output_path:
        today = datetime.now().strftime('%Y-%m-%d')
        output_path = f"docs/prompt_intelligence/{today}_report.md"

    output_path = Path(output_path)

    print(f"Generating report: {output_path}")
    report_generator.generate_report(
        failure_patterns=cross_patterns,
        best_practices=best_practices,
        output_path=output_path,
        top_n=args.top,
    )

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print()

    if blocking > 0:
        print(f"⚠️  {blocking} BLOCKING patterns detected")
        print("   Review report for high-priority fixes")
    elif degraded > 0:
        print(f"✓ No blocking issues, but {degraded} degraded patterns found")
        print("   System functional but could be improved")
    else:
        print("✓ No critical issues detected!")
        print("   System running smoothly")

    print()
    print(f"📄 Full report: {output_path}")
    print()


if __name__ == '__main__':
    main()
