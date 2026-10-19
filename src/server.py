import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP

from .models import ProjectScanResult
from .parsers.scanner import TargetScanner
from .exporters.openapi_exporter import OpenAPIExporter
from .exporters.markdown_exporter import MarkdownExporter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("bytecodelens.server")

mcp = FastMCP(
    name="bytecodelens-java-analyzer",
    host="0.0.0.0",
    port=8088
)

# In-memory scan cache
current_result: Optional[ProjectScanResult] = None

@mcp.tool()
def scan_java_target(target_path: str) -> str:
    """
    扫描指定的 Java 工程目录、.jar 包、.war 包或 .class 文件，逆向解析所有 API 路由与数据库表。
    
    参数:
    - target_path: 目标路径 (例如: 'D:/projects/my-app' 或 '/opt/legacy-system.jar')
    """
    global current_result
    try:
        scanner = TargetScanner(target_path)
        current_result = scanner.scan()
        summary = {
            "target_path": current_result.target_path,
            "scan_mode": current_result.scan_mode,
            "total_classes": current_result.total_classes,
            "total_endpoints": current_result.total_endpoints,
            "total_tables": current_result.total_tables,
            "sample_endpoints": [
                f"{ep.http_method} {ep.path} ({ep.class_name}#{ep.method_name})"
                for ep in current_result.endpoints[:10]
            ],
            "sample_tables": list(current_result.tables.keys())[:10]
        }
        return json.dumps(summary, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False, indent=2)

@mcp.tool()
def list_endpoints(http_method: Optional[str] = None, keyword: Optional[str] = None) -> str:
    """
    检索当前扫描结果中匹配条件的 API 路由清单。
    
    参数:
    - http_method: 过滤请求方式 (例如: 'GET', 'POST', 'PUT', 'DELETE')
    - keyword: 搜索关键字 (匹配路径、方法名或类名)
    """
    if not current_result:
        return json.dumps({"error": "尚未扫描任何目标，请先调用 scan_java_target"}, ensure_ascii=False, indent=2)

    filtered = []
    for ep in current_result.endpoints:
        if http_method and ep.http_method.upper() != http_method.upper():
            continue
        if keyword:
            kw = keyword.lower()
            blob = f"{ep.path} {ep.class_name} {ep.method_name} {ep.summary}".lower()
            if kw not in blob:
                continue
        filtered.append({
            "http_method": ep.http_method,
            "path": ep.path,
            "class_method": f"{ep.class_name}#{ep.method_name}",
            "summary": ep.summary,
            "permissions": ep.permissions,
            "tables": ep.tables
        })

    return json.dumps({
        "matched_count": len(filtered),
        "endpoints": filtered
    }, ensure_ascii=False, indent=2)

@mcp.tool()
def get_endpoint_detail(path_pattern: str) -> str:
    """
    查看指定 API 路由的完整入参规范、返回类型、所需权限及调用的数据库表。
    
    参数:
    - path_pattern: 路由路径模式 (例如: '/api/budget/add')
    """
    if not current_result:
        return json.dumps({"error": "尚未扫描任何目标，请先调用 scan_java_target"}, ensure_ascii=False, indent=2)

    for ep in current_result.endpoints:
        if path_pattern.lower() in ep.path.lower():
            return json.dumps(ep.model_dump(), ensure_ascii=False, indent=2)

    return json.dumps({"error": f"未找到匹配 '{path_pattern}' 的路由"}, ensure_ascii=False, indent=2)

@mcp.tool()
def find_table_usage(table_name: str) -> str:
    """
    逆向影响面分析：查询特定数据库表被哪些 Controller/API 或 Mapper 读写。
    
    参数:
    - table_name: 数据库表名 (例如: 'CT_PURCHASE_ORDER')
    """
    if not current_result:
        return json.dumps({"error": "尚未扫描任何目标，请先调用 scan_java_target"}, ensure_ascii=False, indent=2)

    t_upper = table_name.strip().upper()
    usage = current_result.tables.get(t_upper)
    if not usage:
        return json.dumps({"message": f"在当前工程中未检索到表 '{table_name}' 的显式读写记录"}, ensure_ascii=False, indent=2)

    return json.dumps(usage.model_dump(), ensure_ascii=False, indent=2)

@mcp.tool()
def export_spec(output_format: str = "openapi") -> str:
    """
    将当前 Java 扫描结果全量导出为指定格式 (openapi 或 markdown)。
    
    参数:
    - output_format: 'openapi' (生成 OpenAPI 3.0 JSON) 或 'markdown' (生成 Markdown 拓扑文档)
    """
    if not current_result:
        return json.dumps({"error": "尚未扫描任何目标，请先调用 scan_java_target"}, ensure_ascii=False, indent=2)

    if output_format.lower() == "markdown":
        return MarkdownExporter.to_markdown(current_result)
    else:
        openapi_obj = OpenAPIExporter.to_openapi(current_result)
        return json.dumps(openapi_obj, ensure_ascii=False, indent=2)

def main():
    parser = argparse.ArgumentParser(description="Bytecode-Lens Java Analyzer MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args()

    mcp.settings.host = args.host
    mcp.settings.port = args.port

    logger.info("=" * 60)
    logger.info("  Bytecode-Lens Java Analyzer MCP Server v1.0.0")
    logger.info(f"  Transport: {args.transport.upper()}")
    if args.transport == "sse":
        logger.info(f"  SSE Endpoint: http://{args.host}:{args.port}/sse")
    logger.info("=" * 60)

    mcp.run(transport=args.transport)

if __name__ == "__main__":
    main()
