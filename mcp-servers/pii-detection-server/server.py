#!/usr/bin/env python3
"""
MCP Server for PII Detection and Lake Formation Tagging
========================================================

Custom MCP server that provides tools for:
- PII detection in data lakes
- Lake Formation tag management
- Column-level security configuration

Usage:
    python3 server.py

MCP Configuration:
    Add to ~/.mcp.json or Claude Code settings:
    {
      "mcpServers": {
        "pii-detection": {
          "command": "python3",
          "args": ["/path/to/server.py"]
        }
      }
    }
"""

import json
import sys
import logging
import asyncio
from typing import Any, Dict, List, Optional
import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# AWS clients
glue = boto3.client('glue', region_name='us-east-1')
athena = boto3.client('athena', region_name='us-east-1')
lakeformation = boto3.client('lakeformation', region_name='us-east-1')

# MCP Protocol
class MCPServer:
    def __init__(self):
        self.tools = {
            'detect_pii_in_table': {
                'description': 'Detect PII in a specific table and optionally apply Lake Formation tags',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'database': {'type': 'string', 'description': 'Glue database name'},
                        'table': {'type': 'string', 'description': 'Table name'},
                        'content_detection': {'type': 'boolean', 'description': 'Enable content-based detection (slower but more accurate)', 'default': True},
                        'apply_tags': {'type': 'boolean', 'description': 'Apply LF-Tags to columns', 'default': True}
                    },
                    'required': ['database', 'table']
                }
            },
            'scan_database_for_pii': {
                'description': 'Scan all tables in a database for PII',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'database': {'type': 'string', 'description': 'Glue database name'},
                        'content_detection': {'type': 'boolean', 'description': 'Enable content-based detection', 'default': False},
                        'apply_tags': {'type': 'boolean', 'description': 'Apply LF-Tags to columns', 'default': True}
                    },
                    'required': ['database']
                }
            },
            'create_lf_tags': {
                'description': 'Create Lake Formation tags for PII classification',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'force_recreate': {'type': 'boolean', 'description': 'Recreate tags if they exist', 'default': False}
                    }
                }
            },
            'get_pii_columns': {
                'description': 'Get list of columns tagged with PII in a table',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'database': {'type': 'string', 'description': 'Glue database name'},
                        'table': {'type': 'string', 'description': 'Table name'},
                        'sensitivity_level': {'type': 'string', 'description': 'Filter by sensitivity (CRITICAL, HIGH, MEDIUM, LOW)', 'enum': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']}
                    },
                    'required': ['database', 'table']
                }
            },
            'apply_column_security': {
                'description': 'Apply tag-based access control to columns',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'principal_arn': {'type': 'string', 'description': 'IAM principal ARN'},
                        'sensitivity_levels': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Allowed sensitivity levels'},
                        'database': {'type': 'string', 'description': 'Specific database (optional)'}
                    },
                    'required': ['principal_arn', 'sensitivity_levels']
                }
            },
            'get_pii_report': {
                'description': 'Generate PII report for a database or table',
                'inputSchema': {
                    'type': 'object',
                    'properties': {
                        'database': {'type': 'string', 'description': 'Glue database name'},
                        'table': {'type': 'string', 'description': 'Specific table (optional)'},
                        'format': {'type': 'string', 'description': 'Output format', 'enum': ['json', 'summary'], 'default': 'summary'}
                    },
                    'required': ['database']
                }
            }
        }

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP messages"""
        method = message.get('method')
        params = message.get('params', {})

        if method == 'initialize':
            return {
                'protocolVersion': '2024-11-05',
                'serverInfo': {
                    'name': 'pii-detection-server',
                    'version': '1.0.0'
                },
                'capabilities': {
                    'tools': {}
                }
            }

        elif method == 'tools/list':
            return {'tools': [
                {
                    'name': name,
                    'description': tool['description'],
                    'inputSchema': tool['inputSchema']
                }
                for name, tool in self.tools.items()
            ]}

        elif method == 'tools/call':
            tool_name = params.get('name')
            arguments = params.get('arguments', {})

            if tool_name in self.tools:
                try:
                    result = await self.execute_tool(tool_name, arguments)
                    return {
                        'content': [
                            {
                                'type': 'text',
                                'text': json.dumps(result, indent=2)
                            }
                        ]
                    }
                except Exception as e:
                    logger.error(f"Error executing tool {tool_name}: {e}")
                    return {
                        'content': [
                            {
                                'type': 'text',
                                'text': json.dumps({'error': str(e)})
                            }
                        ],
                        'isError': True
                    }
            else:
                return {
                    'content': [
                        {
                            'type': 'text',
                            'text': json.dumps({'error': f'Unknown tool: {tool_name}'})
                        }
                    ],
                    'isError': True
                }

        return {'error': f'Unknown method: {method}'}

    async def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return results"""

        if tool_name == 'detect_pii_in_table':
            return await self.detect_pii_in_table(
                arguments['database'],
                arguments['table'],
                arguments.get('content_detection', True),
                arguments.get('apply_tags', True)
            )

        elif tool_name == 'scan_database_for_pii':
            return await self.scan_database_for_pii(
                arguments['database'],
                arguments.get('content_detection', False),
                arguments.get('apply_tags', True)
            )

        elif tool_name == 'create_lf_tags':
            return await self.create_lf_tags(
                arguments.get('force_recreate', False)
            )

        elif tool_name == 'get_pii_columns':
            return await self.get_pii_columns(
                arguments['database'],
                arguments['table'],
                arguments.get('sensitivity_level')
            )

        elif tool_name == 'apply_column_security':
            return await self.apply_column_security(
                arguments['principal_arn'],
                arguments['sensitivity_levels'],
                arguments.get('database')
            )

        elif tool_name == 'get_pii_report':
            return await self.get_pii_report(
                arguments['database'],
                arguments.get('table'),
                arguments.get('format', 'summary')
            )

        raise ValueError(f'Tool not implemented: {tool_name}')

    # ========================================================================
    # Tool Implementations
    # ========================================================================

    async def detect_pii_in_table(self, database: str, table: str,
                                   content_detection: bool, apply_tags: bool) -> Dict[str, Any]:
        """Detect PII in a table"""
        logger.info(f"Detecting PII in {database}.{table}")

        # Import PII detection logic
        from pii_detection_and_tagging import (
            scan_table_for_pii,
            apply_lf_tags_to_columns,
            ensure_lf_tags_exist
        )

        # Ensure tags exist
        if apply_tags:
            ensure_lf_tags_exist()

        # Scan table
        pii_results = scan_table_for_pii(database, table, content_detection)

        # Apply tags
        if pii_results and apply_tags:
            apply_lf_tags_to_columns(database, table, pii_results)

        return {
            'database': database,
            'table': table,
            'pii_detected': len(pii_results) > 0,
            'pii_columns': len(pii_results),
            'columns': pii_results
        }

    async def scan_database_for_pii(self, database: str, content_detection: bool,
                                     apply_tags: bool) -> Dict[str, Any]:
        """Scan all tables in database"""
        logger.info(f"Scanning database {database} for PII")

        # Get all tables
        response = glue.get_tables(DatabaseName=database)
        tables = [table['Name'] for table in response['TableList']]

        results = {}
        for table in tables:
            result = await self.detect_pii_in_table(
                database, table, content_detection, apply_tags
            )
            results[table] = result

        total_pii_columns = sum(r['pii_columns'] for r in results.values())
        tables_with_pii = sum(1 for r in results.values() if r['pii_detected'])

        return {
            'database': database,
            'tables_scanned': len(tables),
            'tables_with_pii': tables_with_pii,
            'total_pii_columns': total_pii_columns,
            'results': results
        }

    async def create_lf_tags(self, force_recreate: bool) -> Dict[str, Any]:
        """Create Lake Formation tags"""
        logger.info("Creating Lake Formation tags")

        from pii_detection_and_tagging import ensure_lf_tags_exist

        ensure_lf_tags_exist()

        return {
            'status': 'success',
            'tags_created': ['PII_Classification', 'PII_Type', 'Data_Sensitivity']
        }

    async def get_pii_columns(self, database: str, table: str,
                              sensitivity_level: Optional[str]) -> Dict[str, Any]:
        """Get PII columns from a table"""
        logger.info(f"Getting PII columns from {database}.{table}")

        try:
            # Get tags for all columns
            response = lakeformation.get_resource_lf_tags(
                Resource={
                    'Table': {
                        'DatabaseName': database,
                        'Name': table
                    }
                }
            )

            pii_columns = []

            # Get column-level tags
            if 'LFTagsOnColumns' in response:
                for column_tags in response['LFTagsOnColumns']:
                    column_name = column_tags['Name']
                    tags = {tag['TagKey']: tag['TagValues'][0]
                           for tag in column_tags.get('LFTags', [])}

                    # Filter by sensitivity if specified
                    if sensitivity_level:
                        if tags.get('PII_Classification') == sensitivity_level:
                            pii_columns.append({
                                'column': column_name,
                                'classification': tags.get('PII_Classification'),
                                'type': tags.get('PII_Type'),
                                'sensitivity': tags.get('Data_Sensitivity')
                            })
                    elif 'PII_Classification' in tags:
                        pii_columns.append({
                            'column': column_name,
                            'classification': tags.get('PII_Classification'),
                            'type': tags.get('PII_Type'),
                            'sensitivity': tags.get('Data_Sensitivity')
                        })

            return {
                'database': database,
                'table': table,
                'pii_columns': pii_columns,
                'count': len(pii_columns)
            }

        except ClientError as e:
            return {'error': str(e)}

    async def apply_column_security(self, principal_arn: str,
                                     sensitivity_levels: List[str],
                                     database: Optional[str]) -> Dict[str, Any]:
        """Apply tag-based access control"""
        logger.info(f"Applying column security for {principal_arn}")

        try:
            # Grant permissions based on tags
            lakeformation.grant_permissions(
                Principal={'DataLakePrincipalIdentifier': principal_arn},
                Resource={
                    'LFTagPolicy': {
                        'ResourceType': 'COLUMN',
                        'Expression': [
                            {
                                'TagKey': 'PII_Classification',
                                'TagValues': sensitivity_levels
                            }
                        ]
                    }
                },
                Permissions=['SELECT']
            )

            return {
                'status': 'success',
                'principal': principal_arn,
                'sensitivity_levels': sensitivity_levels,
                'permission': 'SELECT'
            }

        except ClientError as e:
            return {'error': str(e)}

    async def get_pii_report(self, database: str, table: Optional[str],
                             format: str) -> Dict[str, Any]:
        """Generate PII report"""
        logger.info(f"Generating PII report for {database}")

        if table:
            # Single table report
            result = await self.get_pii_columns(database, table, None)

            if format == 'summary':
                return {
                    'database': database,
                    'table': table,
                    'summary': {
                        'total_pii_columns': result['count'],
                        'critical': sum(1 for c in result['pii_columns'] if c['classification'] == 'CRITICAL'),
                        'high': sum(1 for c in result['pii_columns'] if c['classification'] == 'HIGH'),
                        'medium': sum(1 for c in result['pii_columns'] if c['classification'] == 'MEDIUM'),
                        'low': sum(1 for c in result['pii_columns'] if c['classification'] == 'LOW')
                    }
                }
            else:
                return result

        else:
            # Database report
            response = glue.get_tables(DatabaseName=database)
            tables = [t['Name'] for t in response['TableList']]

            all_results = {}
            total_critical = 0
            total_high = 0
            total_medium = 0
            total_low = 0

            for tbl in tables:
                result = await self.get_pii_columns(database, tbl, None)
                if result.get('count', 0) > 0:
                    all_results[tbl] = result
                    for col in result['pii_columns']:
                        if col['classification'] == 'CRITICAL':
                            total_critical += 1
                        elif col['classification'] == 'HIGH':
                            total_high += 1
                        elif col['classification'] == 'MEDIUM':
                            total_medium += 1
                        elif col['classification'] == 'LOW':
                            total_low += 1

            if format == 'summary':
                return {
                    'database': database,
                    'tables_with_pii': len(all_results),
                    'summary': {
                        'critical': total_critical,
                        'high': total_high,
                        'medium': total_medium,
                        'low': total_low
                    }
                }
            else:
                return {
                    'database': database,
                    'tables': all_results
                }


    # ========================================================================
    # MCP Protocol
    # ========================================================================

    async def run(self):
        """Run MCP server"""
        logger.info("Starting PII Detection MCP Server")

        while True:
            try:
                # Read message from stdin
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )

                if not line:
                    break

                message = json.loads(line)
                logger.debug(f"Received message: {message}")

                # Handle message
                response = await self.handle_message(message)
                logger.debug(f"Sending response: {response}")

                # Write response to stdout
                print(json.dumps(response), flush=True)

            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {e}")
                print(json.dumps({'error': 'Invalid JSON'}), flush=True)

            except Exception as e:
                logger.error(f"Error: {e}")
                print(json.dumps({'error': str(e)}), flush=True)


def main():
    """Main entry point"""
    server = MCPServer()
    asyncio.run(server.run())


if __name__ == '__main__':
    main()
