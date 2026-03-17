"""
Enhanced MCP Orchestrator for Agentic Data Onboarding System

Provides detailed, agent-aware logging with:
- Clear agent identification
- MCP server and tool details
- Comprehensive timing information
- Visual separations for readability
- Operation classification
- Resource tracking
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, List
from enum import Enum


class OperationType(Enum):
    """Classification of MCP operations"""
    READ = "READ"           # Query, get, list operations
    WRITE = "WRITE"         # Create, put, update operations
    DELETE = "DELETE"       # Delete, remove operations
    EXECUTE = "EXECUTE"     # Run, start, invoke operations
    VALIDATE = "VALIDATE"   # Check, validate, test operations


class AgentType(Enum):
    """Types of agents in the system"""
    ROUTER = "Router Agent"
    DATA_ONBOARDING = "Data Onboarding Agent"
    METADATA = "Metadata Agent"
    TRANSFORMATION = "Transformation Agent"
    QUALITY = "Quality Agent"
    ANALYSIS = "Analysis Agent"
    ORCHESTRATION = "Orchestration DAG Agent"


class EnhancedMCPOrchestrator:
    """
    Enhanced orchestrator with detailed agent-aware logging.

    Features:
    - Agent tracking and identification
    - Detailed timing breakdowns
    - Operation classification
    - Resource tracking
    - Clear visual separations
    - Cumulative statistics
    """

    def __init__(self, workload_name: str, log_dir: str = "agent_run_logs"):
        self.workload_name = workload_name
        self.log_dir = Path(log_dir) / workload_name
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create detailed log structure
        self.console_log_path = self.log_dir / f"{self.timestamp}_console.log"
        self.json_log_path = self.log_dir / f"{self.timestamp}_structured.json"
        self.agent_logs_dir = self.log_dir / f"{self.timestamp}_agent_logs"
        self.agent_logs_dir.mkdir(exist_ok=True)

        self.steps = []
        self.step_number = 0
        self.current_agent = None
        self.agent_operations = {}  # Track operations per agent
        self.agent_logs = {}  # Separate log per agent
        self.mcp_server_usage = {}  # Track MCP server usage
        self.total_duration = 0.0
        self.operation_start_time = datetime.now()

    def _print_separator(self, char: str = "═", length: int = 100):
        """Print a visual separator line."""
        separator = char * length
        print(separator)
        self._append_to_file(separator)

    def _print_agent_banner(self, agent: AgentType, phase: str):
        """Print agent banner with clear identification."""
        self._print_separator("╔")
        banner = f"║  AGENT: {agent.value:50s}  PHASE: {phase:30s} ║"
        print(banner)
        self._append_to_file(banner)
        self._print_separator("╚")
        print()

    def _print_step_header(self, step_name: str, agent: AgentType):
        """Print step header with agent and step information."""
        self._print_separator("═")
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        header = f"[{timestamp}] STEP {self.step_number}: {step_name}"
        print(header)
        self._append_to_file(header)
        agent_info = f"Agent: {agent.value}"
        print(agent_info)
        self._append_to_file(agent_info)
        self._print_separator("─")

    def _print_detail(self, label: str, value: Any, indent: int = 0):
        """Print detail with consistent formatting."""
        prefix = "  " * indent
        if isinstance(value, dict) or isinstance(value, list):
            print(f"{prefix}{label}:")
            formatted = json.dumps(value, indent=2)
            for line in formatted.split('\n'):
                print(f"{prefix}  {line}")
                self._append_to_file(f"{prefix}  {line}")
        else:
            line = f"{prefix}{label:20s} {value}"
            print(line)
            self._append_to_file(line)

    def _append_to_file(self, text: str):
        """Append text to console log file."""
        with open(self.console_log_path, "a") as f:
            f.write(text + "\n")

        # Also append to current agent's log if an agent is active
        if self.current_agent:
            agent_log_path = self.agent_logs_dir / f"{self.current_agent.value.replace(' ', '_')}.log"
            with open(agent_log_path, "a") as f:
                f.write(text + "\n")

    def _save_json_log(self):
        """Save structured JSON log with statistics."""
        log_data = {
            "workload": self.workload_name,
            "start_time": self.operation_start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "total_duration_seconds": self.total_duration,
            "total_steps": self.step_number,
            "statistics": {
                "operations_per_agent": self.agent_operations,
                "mcp_server_usage": self.mcp_server_usage,
                "success_rate": self._calculate_success_rate()
            },
            "steps": self.steps
        }
        with open(self.json_log_path, "w") as f:
            json.dump(log_data, f, indent=2, default=str)

        # Also save per-agent JSON logs
        self._save_agent_json_logs()

    def _calculate_success_rate(self) -> float:
        """Calculate success rate of operations."""
        if not self.steps:
            return 0.0
        successful = sum(1 for step in self.steps if step["status"] == "✓ SUCCESS")
        return (successful / len(self.steps)) * 100

    def _save_agent_json_logs(self):
        """Save separate JSON logs for each agent."""
        agent_steps = {}

        # Group steps by agent
        for step in self.steps:
            agent_name = step["agent"]
            if agent_name not in agent_steps:
                agent_steps[agent_name] = []
            agent_steps[agent_name].append(step)

        # Save each agent's log
        for agent_name, steps in agent_steps.items():
            agent_stats = self.agent_operations.get(agent_name, {})

            agent_log_data = {
                "agent": agent_name,
                "workload": self.workload_name,
                "timestamp": self.timestamp,
                "statistics": agent_stats,
                "steps": steps
            }

            agent_json_path = self.agent_logs_dir / f"{agent_name.replace(' ', '_')}.json"
            with open(agent_json_path, "w") as f:
                json.dump(agent_log_data, f, indent=2, default=str)

    def _classify_operation(self, tool: str) -> OperationType:
        """Classify operation type based on tool name."""
        tool_lower = tool.lower()
        if any(verb in tool_lower for verb in ['get', 'list', 'describe', 'query', 'scan', 'search', 'lookup']):
            return OperationType.READ
        elif any(verb in tool_lower for verb in ['create', 'put', 'insert', 'update', 'set', 'add']):
            return OperationType.WRITE
        elif any(verb in tool_lower for verb in ['delete', 'remove', 'drop']):
            return OperationType.DELETE
        elif any(verb in tool_lower for verb in ['start', 'run', 'execute', 'invoke', 'trigger']):
            return OperationType.EXECUTE
        elif any(verb in tool_lower for verb in ['validate', 'check', 'test', 'verify']):
            return OperationType.VALIDATE
        else:
            return OperationType.EXECUTE

    def _extract_resources(self, tool: str, params: Dict[str, Any]) -> List[str]:
        """Extract AWS resource identifiers from parameters."""
        resources = []
        resource_keys = [
            'Name', 'DatabaseName', 'TableName', 'JobName', 'CrawlerName',
            'StateMachineArn', 'FunctionName', 'TopicArn', 'RulesetName',
            'ClusterIdentifier', 'Bucket', 'Key', 'database', 'table', 'name'
        ]

        for key in resource_keys:
            if key in params and params[key]:
                resources.append(f"{key}={params[key]}")

        return resources

    def call_mcp(
        self,
        step_name: str,
        agent: AgentType,
        mcp_server: str,
        tool: str,
        params: Dict[str, Any],
        description: Optional[str] = None,
        expected_duration: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Call an MCP server tool with enhanced logging.

        Args:
            step_name: Human-readable step name
            agent: Agent executing this operation
            mcp_server: MCP server name (from .mcp.json)
            tool: Tool/method name on the MCP server
            params: Tool parameters
            description: Optional step description
            expected_duration: Expected duration in seconds (for performance tracking)

        Returns:
            Result from MCP call
        """
        self.step_number += 1
        operation_type = self._classify_operation(tool)
        resources = self._extract_resources(tool, params)

        # Track agent operations
        agent_name = agent.value
        if agent_name not in self.agent_operations:
            self.agent_operations[agent_name] = {
                "total_operations": 0,
                "successful": 0,
                "failed": 0,
                "total_duration": 0.0
            }

        # Track MCP server usage
        if mcp_server not in self.mcp_server_usage:
            self.mcp_server_usage[mcp_server] = {
                "call_count": 0,
                "total_duration": 0.0,
                "operations": []
            }

        # Start timing
        step_start = datetime.now()
        start_time = time.time()

        # Print step header
        self._print_step_header(step_name, agent)

        # Print operation details
        print()
        self._print_detail("⚙️  Operation Type", operation_type.value)
        if description:
            self._print_detail("📝 Description", description)
        self._print_detail("🔧 MCP Server", mcp_server)
        self._print_detail("🛠️  Tool", tool)

        if resources:
            self._print_detail("📦 Resources", resources)

        if expected_duration:
            self._print_detail("⏱️  Expected Duration", f"~{expected_duration:.1f}s")

        print()
        self._print_detail("📥 Input Parameters", params, indent=1)
        print()

        self._print_separator("┈")
        exec_start = datetime.now()
        print(f"⚡ Executing at {exec_start.strftime('%H:%M:%S.%f')[:-3]}...")
        print()

        # Execute MCP call
        try:
            result = self._execute_mcp_call(mcp_server, tool, params)
            status = "✓ SUCCESS"
            status_icon = "✅"
            error = None

            # Update success counters
            self.agent_operations[agent_name]["successful"] += 1

        except Exception as e:
            result = None
            status = "✗ FAILED"
            status_icon = "❌"
            error = str(e)

            # Update failure counters
            self.agent_operations[agent_name]["failed"] += 1

        # Calculate timings
        duration = time.time() - start_time
        exec_end = datetime.now()

        # Update duration trackers
        self.total_duration += duration
        self.agent_operations[agent_name]["total_duration"] += duration
        self.agent_operations[agent_name]["total_operations"] += 1
        self.mcp_server_usage[mcp_server]["call_count"] += 1
        self.mcp_server_usage[mcp_server]["total_duration"] += duration
        self.mcp_server_usage[mcp_server]["operations"].append(tool)

        # Print result
        self._print_separator("─")
        print()
        self._print_detail("🎯 Status", f"{status_icon} {status}")

        if error:
            self._print_detail("❌ Error", error)
        else:
            print()
            self._print_detail("📤 Output", result, indent=1)

        print()
        self._print_detail("⏱️  Timing Details", {
            "Start": step_start.strftime("%H:%M:%S.%f")[:-3],
            "End": exec_end.strftime("%H:%M:%S.%f")[:-3],
            "Duration": f"{duration:.3f}s"
        })

        # Performance indicator
        if expected_duration:
            if duration <= expected_duration:
                perf_icon = "🚀"
                perf_msg = f"Faster than expected ({duration:.2f}s vs {expected_duration:.2f}s)"
            else:
                perf_icon = "🐌"
                perf_msg = f"Slower than expected ({duration:.2f}s vs {expected_duration:.2f}s)"
            self._print_detail(f"{perf_icon} Performance", perf_msg)

        self._print_separator("═")
        print()

        # Log to JSON
        step_log = {
            "step_number": self.step_number,
            "step_name": step_name,
            "agent": agent.value,
            "description": description,
            "mcp_server": mcp_server,
            "tool": tool,
            "operation_type": operation_type.value,
            "resources": resources,
            "params": params,
            "result": result,
            "status": status,
            "error": error,
            "timing": {
                "start": step_start.isoformat(),
                "end": exec_end.isoformat(),
                "duration_seconds": duration,
                "expected_duration": expected_duration
            }
        }
        self.steps.append(step_log)
        self._save_json_log()

        if error:
            raise Exception(f"MCP call failed: {error}")

        return result

    def _execute_mcp_call(self, mcp_server: str, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute actual MCP call via boto3 AWS SDK.

        Production implementation - calls real AWS services via MCP servers.
        Each MCP server maps to specific AWS service clients.
        """
        import boto3

        try:
            if mcp_server == "aws-dataprocessing":
                return self._call_aws_dataprocessing(tool, params)
            elif mcp_server == "dynamodb":
                return self._call_dynamodb(tool, params)
            elif mcp_server == "s3-tables":
                return self._call_s3_tables(tool, params)
            elif mcp_server == "sagemaker-catalog":
                return self._call_sagemaker_catalog(tool, params)
            elif mcp_server == "s3":
                return self._call_s3(tool, params)
            elif mcp_server == "local-filesystem":
                return self._call_local_filesystem(tool, params)
            else:
                raise ValueError(f"Unknown MCP server: {mcp_server}")
        except Exception as e:
            logger.error("MCP call failed: server=%s, tool=%s, error=%s", mcp_server, tool, str(e))
            raise

    def _call_aws_dataprocessing(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call AWS Glue/Athena via aws-dataprocessing MCP server."""
        import boto3

        if tool == "create_crawler":
            glue = boto3.client('glue')
            response = glue.create_crawler(**params)
            return {
                "CrawlerName": params.get("Name"),
                "Status": "CREATED",
                "Message": "Crawler created successfully"
            }
        elif tool == "start_crawler":
            glue = boto3.client('glue')
            response = glue.start_crawler(Name=params.get("Name"))
            return {
                "CrawlerName": params.get("Name"),
                "Status": "STARTING",
                "Message": "Crawler started successfully"
            }
        elif tool == "start_query_execution":
            athena = boto3.client('athena')
            response = athena.start_query_execution(**params)
            return {
                "QueryExecutionId": response["QueryExecutionId"],
                "Status": "RUNNING",
                "Message": "Query started successfully"
            }
        elif tool == "create_job":
            glue = boto3.client('glue')
            response = glue.create_job(**params)
            return {
                "Name": params.get("Name"),
                "Status": "CREATED",
                "Message": "Glue job created successfully"
            }
        elif tool == "start_job_run":
            glue = boto3.client('glue')
            response = glue.start_job_run(**params)
            return {
                "JobRunId": response["JobRunId"],
                "Status": "STARTING",
                "Message": "Job run started successfully"
            }
        elif tool == "start_data_quality_ruleset_evaluation_run":
            glue = boto3.client('glue')
            response = glue.start_data_quality_ruleset_evaluation_run(**params)
            return {
                "RunId": response["RunId"],
                "Status": "STARTING",
                "Message": "Data quality evaluation started"
            }
        else:
            raise ValueError(f"Unknown aws-dataprocessing tool: {tool}")

    def _call_dynamodb(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call DynamoDB via dynamodb MCP server."""
        import boto3

        dynamodb = boto3.client('dynamodb')

        if tool == "put_item":
            response = dynamodb.put_item(**params)
            return {
                "TableName": params.get("TableName"),
                "Status": "SUCCESS",
                "Message": "Item stored successfully"
            }
        elif tool == "get_item":
            response = dynamodb.get_item(**params)
            return {
                "Item": response.get("Item"),
                "Status": "SUCCESS",
                "Message": "Item retrieved successfully"
            }
        elif tool == "query":
            response = dynamodb.query(**params)
            return {
                "Items": response.get("Items", []),
                "Count": response.get("Count", 0),
                "Status": "SUCCESS",
                "Message": "Query executed successfully"
            }
        else:
            raise ValueError(f"Unknown dynamodb tool: {tool}")

    def _call_s3_tables(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call S3 Tables (Iceberg) via s3-tables MCP server."""
        import boto3

        s3tables = boto3.client('s3tables')

        if tool == "create_table":
            response = s3tables.create_table(**params)
            return {
                "TableName": params.get("name"),
                "Format": "ICEBERG",
                "Status": "CREATED",
                "TableArn": response.get("tableArn"),
                "Message": "S3 Table created successfully"
            }
        elif tool == "get_table":
            response = s3tables.get_table(**params)
            return {
                "Table": response,
                "Status": "SUCCESS",
                "Message": "Table retrieved successfully"
            }
        else:
            raise ValueError(f"Unknown s3-tables tool: {tool}")

    def _call_sagemaker_catalog(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call SageMaker Catalog custom metadata via sagemaker-catalog MCP server."""
        import boto3

        glue = boto3.client('glue')

        if tool == "put_custom_metadata":
            # Update Glue table with custom metadata in Parameters
            database = params.get("database")
            table = params.get("table")
            custom_metadata = params.get("custom_metadata")

            # Get existing table
            response = glue.get_table(DatabaseName=database, Name=table)
            table_input = response['Table']

            # Add custom metadata to Parameters
            if 'Parameters' not in table_input:
                table_input['Parameters'] = {}
            table_input['Parameters']['custom_metadata'] = json.dumps(custom_metadata)

            # Remove read-only fields
            for key in ['DatabaseName', 'CreateTime', 'UpdateTime', 'CreatedBy', 'IsRegisteredWithLakeFormation', 'CatalogId', 'VersionId']:
                table_input.pop(key, None)

            # Update table
            glue.update_table(DatabaseName=database, TableInput=table_input)

            return {
                "database": database,
                "table": table,
                "status": "SUCCESS",
                "Message": "Custom metadata stored successfully"
            }
        else:
            raise ValueError(f"Unknown sagemaker-catalog tool: {tool}")

    def _call_s3(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call S3 via s3 MCP server."""
        import boto3

        s3 = boto3.client('s3')

        if tool == "put_object":
            response = s3.put_object(**params)
            return {
                "Bucket": params.get("Bucket"),
                "Key": params.get("Key"),
                "Status": "SUCCESS",
                "Message": "Object uploaded successfully"
            }
        elif tool == "get_object":
            response = s3.get_object(**params)
            return {
                "Body": response['Body'].read(),
                "Status": "SUCCESS",
                "Message": "Object retrieved successfully"
            }
        else:
            raise ValueError(f"Unknown s3 tool: {tool}")

    def _call_local_filesystem(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call local filesystem via local-filesystem MCP server."""
        import os
        import yaml

        if tool == "list_workloads":
            workloads_dir = params.get("workloads_dir", "workloads")
            workloads = []
            for item in os.listdir(workloads_dir):
                if os.path.isdir(os.path.join(workloads_dir, item)):
                    workloads.append(item)
            return {
                "workloads": workloads,
                "count": len(workloads),
                "Status": "SUCCESS",
                "Message": "Workloads listed successfully"
            }
        elif tool == "read_config":
            config_path = params.get("config_path")
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return {
                "config": config,
                "Status": "SUCCESS",
                "Message": "Config read successfully"
            }
        else:
            raise ValueError(f"Unknown local-filesystem tool: {tool}")

    def start_agent_phase(self, agent: AgentType, phase: str):
        """Start a new agent phase with banner."""
        self.current_agent = agent

        # Create agent log file if it doesn't exist
        agent_log_path = self.agent_logs_dir / f"{agent.value.replace(' ', '_')}.log"
        if not agent_log_path.exists():
            with open(agent_log_path, "w") as f:
                f.write(f"{'═' * 100}\n")
                f.write(f"AGENT LOG: {agent.value}\n")
                f.write(f"Workload: {self.workload_name}\n")
                f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'═' * 100}\n\n")

        self._print_agent_banner(agent, phase)

    def agent_summary(self, agent: AgentType, summary: str, resources_created: List[str] = None):
        """Print agent phase summary with statistics."""
        agent_name = agent.value
        stats = self.agent_operations.get(agent_name, {})

        self._print_separator("╔")
        print(f"║  AGENT COMPLETE: {agent_name:70s} ║")
        self._print_separator("╚")
        print()

        print("📊 Statistics:")
        if stats:
            self._print_detail("  Total Operations", stats.get("total_operations", 0))
            self._print_detail("  Successful", stats.get("successful", 0))
            self._print_detail("  Failed", stats.get("failed", 0))
            self._print_detail("  Total Duration", f"{stats.get('total_duration', 0):.2f}s")

        if resources_created:
            print()
            print("📦 Resources Created:")
            for resource in resources_created:
                print(f"  ✓ {resource}")
                self._append_to_file(f"  ✓ {resource}")

        print()
        print("📝 Summary:")
        for line in summary.strip().split('\n'):
            print(f"  {line.strip()}")
            self._append_to_file(f"  {line.strip()}")

        self._print_separator("═")
        print()

    def final_summary(self):
        """Print final summary with all statistics."""
        end_time = datetime.now()
        elapsed = end_time - self.operation_start_time

        self._print_separator("╔")
        print(f"║  FINAL SUMMARY - {self.workload_name:70s} ║")
        self._print_separator("╚")
        print()

        print("⏱️  Overall Timing:")
        self._print_detail("  Start Time", self.operation_start_time.strftime("%Y-%m-%d %H:%M:%S"))
        self._print_detail("  End Time", end_time.strftime("%Y-%m-%d %H:%M:%S"))
        self._print_detail("  Total Elapsed", str(elapsed).split('.')[0])
        self._print_detail("  Total Operation Time", f"{self.total_duration:.2f}s")

        print()
        print("📊 Operations Summary:")
        self._print_detail("  Total Steps", self.step_number)
        success_rate = self._calculate_success_rate()
        self._print_detail("  Success Rate", f"{success_rate:.1f}%")

        print()
        print("🤖 Agent Breakdown:")
        for agent_name, stats in sorted(self.agent_operations.items()):
            print(f"\n  {agent_name}:")
            self._print_detail("    Operations", stats["total_operations"], indent=1)
            self._print_detail("    Duration", f"{stats['total_duration']:.2f}s", indent=1)
            self._print_detail("    Success Rate",
                             f"{(stats['successful']/stats['total_operations']*100):.1f}%" if stats['total_operations'] > 0 else "N/A",
                             indent=1)

        print()
        print("🔧 MCP Server Usage:")
        for server, stats in sorted(self.mcp_server_usage.items(), key=lambda x: x[1]['call_count'], reverse=True):
            print(f"\n  {server}:")
            self._print_detail("    Calls", stats["call_count"], indent=1)
            self._print_detail("    Duration", f"{stats['total_duration']:.2f}s", indent=1)
            self._print_detail("    Avg per call", f"{stats['total_duration']/stats['call_count']:.3f}s" if stats['call_count'] > 0 else "N/A", indent=1)

        print()
        print("📁 Log Files:")
        self._print_detail("  Master Console Log", str(self.console_log_path))
        self._print_detail("  Master JSON Log", str(self.json_log_path))
        self._print_detail("  Agent Logs Directory", str(self.agent_logs_dir))

        # List agent-specific logs
        agent_log_files = list(self.agent_logs_dir.glob("*.log"))
        if agent_log_files:
            print()
            print("  Per-Agent Logs:")
            for log_file in sorted(agent_log_files):
                print(f"    ✓ {log_file.name}")
                self._append_to_file(f"    ✓ {log_file.name}")

        agent_json_files = list(self.agent_logs_dir.glob("*.json"))
        if agent_json_files:
            print()
            print("  Per-Agent JSON:")
            for json_file in sorted(agent_json_files):
                print(f"    ✓ {json_file.name}")
                self._append_to_file(f"    ✓ {json_file.name}")

        self._print_separator("═")
        print()


# Example Usage
if __name__ == "__main__":
    # Initialize enhanced orchestrator
    orch = EnhancedMCPOrchestrator(workload_name="sales_transactions")

    # Phase 1: Router Agent
    orch.start_agent_phase(AgentType.ROUTER, "Phase 1: Check Existing Workloads")

    orch.call_mcp(
        step_name="Check Existing Workload",
        agent=AgentType.ROUTER,
        mcp_server="local-filesystem",
        tool="list_workloads",
        params={},
        description="Router Agent checks if data already onboarded",
        expected_duration=1.0
    )

    orch.agent_summary(
        AgentType.ROUTER,
        summary="✓ Scanned workloads/ directory\n✓ No duplicate sources found\n→ Proceeding to onboarding",
        resources_created=[]
    )

    # Phase 3: Metadata Agent
    orch.start_agent_phase(AgentType.METADATA, "Phase 3: Schema Discovery & Profiling")

    orch.call_mcp(
        step_name="Schema Discovery (Glue Crawler)",
        agent=AgentType.METADATA,
        mcp_server="aws-dataprocessing",
        tool="create_crawler",
        params={
            "Name": "sales_transactions_crawler",
            "Role": "arn:aws:iam::123456789012:role/GlueCrawlerRole",
            "DatabaseName": "sales_transactions_db",
            "Targets": {
                "S3Targets": [{
                    "Path": "s3://data-bronze/sales_transactions/"
                }]
            }
        },
        description="Discover schema from raw S3 data using Glue Crawler",
        expected_duration=3.0
    )

    orch.call_mcp(
        step_name="Data Profiling (Athena 5% Sample)",
        agent=AgentType.METADATA,
        mcp_server="aws-dataprocessing",
        tool="start_query_execution",
        params={
            "QueryString": "SELECT COUNT(*) FROM sales_transactions TABLESAMPLE BERNOULLI(5)",
            "QueryExecutionContext": {
                "Database": "sales_transactions_db"
            }
        },
        description="Profile data quality and statistics on 5% sample",
        expected_duration=15.0
    )

    orch.call_mcp(
        step_name="Store Business Metadata",
        agent=AgentType.METADATA,
        mcp_server="sagemaker-catalog",
        tool="put_custom_metadata",
        params={
            "database": "sales_transactions_db",
            "table": "sales_transactions_silver",
            "custom_metadata": {
                "columns": {
                    "revenue": {"role": "measure", "default_aggregation": "sum"}
                }
            }
        },
        description="Store column roles and business context",
        expected_duration=1.0
    )

    orch.agent_summary(
        AgentType.METADATA,
        summary="✓ Schema discovered via Glue Crawler\n✓ Data profiled via Athena\n✓ Business metadata stored",
        resources_created=[
            "Glue Crawler: sales_transactions_crawler",
            "Glue Database: sales_transactions_db",
            "SageMaker Catalog Metadata: sales_transactions_silver"
        ]
    )

    # Final summary
    orch.final_summary()
