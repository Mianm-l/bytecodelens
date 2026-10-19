import os
from pathlib import Path
from typing import Dict, List, Optional
import zipfile

from ..models import EndpointInfo, ProjectScanResult, TableUsage
from .class_parser import ClassBytecodeParser
from .source_parser import JavaSourceParser
from .mybatis_parser import MyBatisParser

class TargetScanner:
    """Scans Java projects, Jar/War files, and class directories."""

    def __init__(self, target_path: str):
        self.target_path = Path(target_path).resolve()
        self.endpoints: List[EndpointInfo] = []
        self.tables: Dict[str, TableUsage] = {}
        self.total_classes = 0

    def scan(self) -> ProjectScanResult:
        if not self.target_path.exists():
            raise FileNotFoundError(f"Target path does not exist: {self.target_path}")

        scan_mode = "source"
        if self.target_path.is_file() and self.target_path.suffix.lower() in (".jar", ".war", ".zip"):
            scan_mode = "bytecode"
            self._scan_jar(self.target_path)
        elif self.target_path.is_file() and self.target_path.suffix.lower() == ".class":
            scan_mode = "bytecode"
            self._scan_class_file(self.target_path)
        elif self.target_path.is_dir():
            scan_mode = "hybrid"
            self._scan_directory(self.target_path)

        # Cross-reference endpoints with tables
        for ep in self.endpoints:
            # If endpoint has no tables yet, infer from package name matching mapper
            ep_pkg = ".".join(ep.class_name.split(".")[:-1])
            for t_name, usage in self.tables.items():
                if usage.mapper_id and ep_pkg and ep_pkg in usage.mapper_id:
                    if t_name not in ep.tables:
                        ep.tables.append(t_name)
                if ep.path not in usage.referenced_by_endpoints and t_name in ep.tables:
                    usage.referenced_by_endpoints.append(f"{ep.http_method} {ep.path}")

        return ProjectScanResult(
            target_path=str(self.target_path),
            scan_mode=scan_mode,
            total_classes=self.total_classes,
            total_endpoints=len(self.endpoints),
            total_tables=len(self.tables),
            endpoints=self.endpoints,
            tables=self.tables
        )

    def _scan_jar(self, jar_file: Path) -> None:
        with zipfile.ZipFile(jar_file, "r") as z:
            for name in z.namelist():
                lower = name.lower()
                if lower.endswith(".class") and not lower.endswith("module-info.class"):
                    self.total_classes += 1
                    try:
                        data = z.read(name)
                        parser = ClassBytecodeParser(data)
                        parser.parse()
                        self.endpoints.extend(parser.extract_endpoints())
                        for t in parser.sql_tables:
                            if t not in self.tables:
                                self.tables[t] = TableUsage(table_name=t, operations=["SELECT"])
                    except Exception:
                        pass
                elif lower.endswith(".xml") and ("mapper" in lower or "dao" in lower):
                    try:
                        content = z.read(name).decode("utf-8", errors="replace")
                        m_parser = MyBatisParser(content)
                        parsed_tables = m_parser.parse()
                        for t, u in parsed_tables.items():
                            if t not in self.tables:
                                self.tables[t] = u
                            else:
                                for op in u.operations:
                                    if op not in self.tables[t].operations:
                                        self.tables[t].operations.append(op)
                    except Exception:
                        pass

    def _scan_class_file(self, class_file: Path) -> None:
        self.total_classes += 1
        with open(class_file, "rb") as f:
            parser = ClassBytecodeParser(f.read())
            parser.parse()
            self.endpoints.extend(parser.extract_endpoints())
            for t in parser.sql_tables:
                if t not in self.tables:
                    self.tables[t] = TableUsage(table_name=t, operations=["SELECT"])

    def _scan_directory(self, dir_path: Path) -> None:
        for root, _, files in os.walk(dir_path):
            for file in files:
                ext = file.lower().split(".")[-1]
                full_path = Path(root) / file

                if ext == "class" and not file.lower().endswith("module-info.class"):
                    self.total_classes += 1
                    try:
                        with open(full_path, "rb") as f:
                            parser = ClassBytecodeParser(f.read())
                            parser.parse()
                            self.endpoints.extend(parser.extract_endpoints())
                            for t in parser.sql_tables:
                                if t not in self.tables:
                                    self.tables[t] = TableUsage(table_name=t, operations=["SELECT"])
                    except Exception:
                        pass

                elif ext == "java":
                    self.total_classes += 1
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                            s_parser = JavaSourceParser(f.read(), str(full_path))
                            parsed_eps = s_parser.parse()
                            self.endpoints.extend(parsed_eps)
                            for ep in parsed_eps:
                                for t in ep.tables:
                                    if t not in self.tables:
                                        self.tables[t] = TableUsage(table_name=t, operations=["SELECT"])
                    except Exception:
                        pass

                elif ext == "xml" and ("mapper" in file.lower() or "dao" in file.lower()):
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                            m_parser = MyBatisParser(f.read())
                            parsed_tables = m_parser.parse()
                            for t, u in parsed_tables.items():
                                if t not in self.tables:
                                    self.tables[t] = u
                                else:
                                    for op in u.operations:
                                        if op not in self.tables[t].operations:
                                            self.tables[t].operations.append(op)
                    except Exception:
                        pass
