import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Tuple
from ..models import TableUsage

TABLE_REGEX = re.compile(
    r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+([a-zA-Z0-9_]{3,32})\b",
    re.IGNORECASE
)
EXCLUDE_TABLES = {"DUAL", "SET", "VALUES", "WHERE", "SELECT", "NULL", "AND", "OR", "ON", "AS"}

class MyBatisParser:
    """Parses MyBatis Mapper XML files to extract SQL statements and table dependencies."""

    def __init__(self, xml_content: str):
        self.content = xml_content

    def parse(self) -> Dict[str, TableUsage]:
        """
        Returns a mapping of table_name -> TableUsage
        """
        table_usages: Dict[str, TableUsage] = {}

        try:
            root = ET.fromstring(self.content)
            namespace = root.attrib.get("namespace", "UnknownMapper")

            for child in root:
                tag = child.tag.lower()
                op = None
                if tag == "select":
                    op = "SELECT"
                elif tag == "insert":
                    op = "INSERT"
                elif tag == "update":
                    op = "UPDATE"
                elif tag == "delete":
                    op = "DELETE"

                if not op:
                    continue

                mapper_id = child.attrib.get("id", "")
                sql_text = "".join(child.itertext())

                # Find tables
                for t_match in TABLE_REGEX.findall(sql_text):
                    t = t_match.upper()
                    if t not in EXCLUDE_TABLES and len(t) > 3:
                        if t not in table_usages:
                            table_usages[t] = TableUsage(
                                table_name=t,
                                operations=[],
                                mapper_id=f"{namespace}#{mapper_id}"
                            )
                        if op not in table_usages[t].operations:
                            table_usages[t].operations.append(op)
        except Exception:
            # Fallback regex parsing if XML is malformed
            for match in re.finditer(r"<(select|insert|update|delete)\b[^>]*>(.*?)</\1>", self.content, re.DOTALL | re.IGNORECASE):
                op = match.group(1).upper()
                sql = match.group(2)
                for t_match in TABLE_REGEX.findall(sql):
                    t = t_match.upper()
                    if t not in EXCLUDE_TABLES and len(t) > 3:
                        if t not in table_usages:
                            table_usages[t] = TableUsage(table_name=t, operations=[])
                        if op not in table_usages[t].operations:
                            table_usages[t].operations.append(op)

        return table_usages
