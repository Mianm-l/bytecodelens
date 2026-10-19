from ..models import ProjectScanResult

class MarkdownExporter:
    @staticmethod
    def to_markdown(result: ProjectScanResult) -> str:
        lines = [
            f"# Bytecode-Lens 接口与数据库表调用拓扑报告",
            f"",
            f"> **扫描目标**：`{result.target_path}`  ",
            f"> **扫描模式**：`{result.scan_mode}`  ",
            f"> **解析类总数**：`{result.total_classes}` | **发现 API 路由**：`{result.total_endpoints}` | **关联数据库表**：`{result.total_tables}`",
            f"",
            f"---",
            f"",
            f"## 1. 核心接口与数据库表调用链路图",
            f"",
            f"```mermaid",
            f"flowchart LR"
        ]

        # Add Mermaid nodes for top endpoints and tables
        sample_endpoints = result.endpoints[:8]
        for idx, ep in enumerate(sample_endpoints):
            ep_id = f"EP_{idx}"
            ep_label = f"{ep.http_method} {ep.path}"
            lines.append(f'    {ep_id}["{ep_label}"]')
            for t in ep.tables[:3]:
                t_id = f"TBL_{t.replace('_', '')}"
                lines.append(f'    {t_id}[("表: {t}")]')
                lines.append(f'    {ep_id} -->|CRUD| {t_id}')

        lines.extend([
            f"```",
            f"",
            f"---",
            f"",
            f"## 2. API 路由规范总览",
            f"",
            f"| 请求方法 | 路由路径 | 所属 Java 类与方法 | 权限要求 | 触达数据库表 |",
            f"| :--- | :--- | :--- | :--- | :--- |"
        ])

        for ep in result.endpoints:
            perms_str = "<br>".join([f"`{p}`" for p in ep.permissions]) if ep.permissions else "*(公开/无显式注解)*"
            tables_str = ", ".join([f"`{t}`" for t in ep.tables]) if ep.tables else "-"
            simple_class = ep.class_name.split(".")[-1]
            lines.append(
                f"| `{ep.http_method}` | **{ep.path}** | `{simple_class}#{ep.method_name}` | {perms_str} | {tables_str} |"
            )

        lines.extend([
            f"",
            f"---",
            f"",
            f"## 3. 数据库表影响面矩阵 (Table Access Matrix)",
            f"",
            f"| 数据库表名 | 涉及操作 (CRUD) | 关联的 Mapper 映射 | 调用该表的 API 接口 |",
            f"| :--- | :--- | :--- | :--- |"
        ])

        for tbl_name, usage in result.tables.items():
            ops_str = ", ".join(usage.operations) if usage.operations else "SELECT"
            mapper_str = f"`{usage.mapper_id}`" if usage.mapper_id else "-"
            ep_str = "<br>".join([f"`{e}`" for e in usage.referenced_by_endpoints[:5]]) if usage.referenced_by_endpoints else "-"
            lines.append(f"| **`{tbl_name}`** | {ops_str} | {mapper_str} | {ep_str} |")

        return "\n".join(lines)
