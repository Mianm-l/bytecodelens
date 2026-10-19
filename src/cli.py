import argparse
import json
import sys
from pathlib import Path
from .parsers.scanner import TargetScanner
from .exporters.openapi_exporter import OpenAPIExporter
from .exporters.markdown_exporter import MarkdownExporter

def main():
    parser = argparse.ArgumentParser(
        description="Bytecode-Lens: Pure-Python Java Legacy System Reverse Engineering Tool"
    )
    parser.add_argument("target", help="Path to .jar, .war, .class or Java project directory")
    parser.add_argument(
        "--format",
        choices=["openapi", "markdown", "json"],
        default="markdown",
        help="Export format (default: markdown)"
    )
    parser.add_argument("--output", "-o", help="Output file path (default: print to stdout)")
    args = parser.parse_args()

    print(f"[*] Scanning Java target: {args.target}...", file=sys.stderr)
    scanner = TargetScanner(args.target)
    result = scanner.scan()

    print(
        f"[+] Done! Found {result.total_classes} classes, {result.total_endpoints} endpoints, {result.total_tables} database tables.",
        file=sys.stderr
    )

    if args.format == "markdown":
        out_content = MarkdownExporter.to_markdown(result)
    elif args.format == "openapi":
        spec = OpenAPIExporter.to_openapi(result)
        out_content = json.dumps(spec, ensure_ascii=False, indent=2)
    else:
        out_content = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(out_content)
        print(f"[+] Output successfully written to: {args.output}", file=sys.stderr)
    else:
        print(out_content)

if __name__ == "__main__":
    main()
