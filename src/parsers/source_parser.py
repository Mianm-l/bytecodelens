import re
from typing import Dict, List, Optional, Set, Tuple
from ..models import EndpointInfo, EndpointParam

TABLE_SQL_REGEX = re.compile(
    r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+([a-zA-Z0-9_]{3,32})\b",
    re.IGNORECASE
)
EXCLUDE_TABLES = {"DUAL", "SET", "VALUES", "WHERE", "SELECT", "NULL", "AND", "OR", "ON", "AS"}

class JavaSourceParser:
    """Parses .java source files for Spring / RuoYi / Seeyon endpoints and tables."""

    def __init__(self, code: str, file_path: str = ""):
        self.code = code
        self.file_path = file_path

    def parse(self) -> List[EndpointInfo]:
        endpoints = []

        # 1. Package
        pkg_match = re.search(r"package\s+([a-zA-Z0-9_\.]+);", self.code)
        package_name = pkg_match.group(1) if pkg_match else ""

        # 2. Class definition & annotations
        class_match = re.search(r"public\s+class\s+([a-zA-Z0-9_]+)", self.code)
        if not class_match:
            return []
        class_name = class_match.group(1)
        full_class_name = f"{package_name}.{class_name}" if package_name else class_name

        # Check if it's a Controller
        is_controller = bool(re.search(r"@(Rest)?Controller\b", self.code[:class_match.start()]))
        if not is_controller:
            return []

        # Base path
        base_match = re.search(r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']+)[\"']", self.code[:class_match.start()])
        base_path = base_match.group(1) if base_match else ""
        if base_path and not base_path.startswith('/'):
            base_path = '/' + base_path
        if base_path.endswith('/'):
            base_path = base_path[:-1]

        # Match method signatures: public [Type] [name]([params])
        method_sig_pattern = re.compile(
            r"public\s+([\w<>\[\],\s]+)\s+([a-zA-Z0-9_]+)\s*\((.*?)\)\s*\{",
            re.DOTALL
        )

        class_body = self.code[class_match.end():]
        last_end = 0

        for m in method_sig_pattern.finditer(class_body):
            header_block = class_body[last_end : m.start()]
            last_end = m.end()

            ret_type = m.group(1).strip()
            method_name = m.group(2)
            params_raw = m.group(3).strip()

            http_method = None
            m_path = ""
            perms = []

            # Extract mapping annotations using balanced paren
            def get_ann_arg(ann_name: str) -> Optional[str]:
                idx = header_block.find(ann_name)
                if idx == -1:
                    return None
                open_p = header_block.find('(', idx)
                if open_p == -1:
                    return ""
                # ensure paren is on same line or right after
                if '\n' in header_block[idx:open_p] and not header_block[idx:open_p].strip().startswith('('):
                    return ""
                depth = 0
                for i in range(open_p, len(header_block)):
                    if header_block[i] == '(':
                        depth += 1
                    elif header_block[i] == ')':
                        depth -= 1
                        if depth == 0:
                            return header_block[open_p + 1 : i]
                return None

            for method_type, ann_key in [("GET", "@GetMapping"), ("POST", "@PostMapping"),
                                         ("PUT", "@PutMapping"), ("DELETE", "@DeleteMapping"),
                                         ("ANY", "@RequestMapping")]:
                arg = get_ann_arg(ann_key)
                if arg is not None:
                    http_method = method_type if method_type != "ANY" else "POST"
                    if "method" in arg:
                        m_type_match = re.search(r"RequestMethod\.([A-Z]+)", arg)
                        if m_type_match:
                            http_method = m_type_match.group(1)
                    # Extract path from quotes
                    path_match = re.search(r"[\"']([^\"']*)[\"']", arg)
                    if path_match:
                        m_path = path_match.group(1)
                    break

            if not http_method:
                continue

            # Extract permissions (@PreAuthorize or @RequiresPermissions)
            for perm_ann in ["@PreAuthorize", "@RequiresPermissions"]:
                p_arg = get_ann_arg(perm_ann)
                if p_arg:
                    p_clean = p_arg.strip()
                    if (p_clean.startswith('"') and p_clean.endswith('"')) or (p_clean.startswith("'") and p_clean.endswith("'")):
                        p_clean = p_clean[1:-1]
                    found = re.findall(r"['\"]([^'\"]+)['\"]", p_clean)
                    perms.extend(found if found else [p_clean])

            # Extract Javadoc
            summary = None
            jd_match = re.search(r"/\*\*(.*?)\*/", header_block, re.DOTALL)
            if jd_match:
                lines = [l.strip().lstrip('*').strip() for l in jd_match.group(1).splitlines()]
                lines = [l for l in lines if l and not l.startswith('@')]
                if lines:
                    summary = lines[0]

            # Full path
            if m_path and not m_path.startswith('/'):
                m_path = '/' + m_path
            full_path = f"{base_path}{m_path}" or "/"

            # Parameters
            params = []
            if params_raw:
                for param_str in params_raw.split(','):
                    param_str = param_str.strip()
                    if not param_str:
                        continue
                    tokens = param_str.split()
                    p_name = tokens[-1]
                    p_type = tokens[-2] if len(tokens) >= 2 else "Object"
                    in_loc = "query"
                    if "@RequestBody" in param_str:
                        in_loc = "body"
                    elif "@PathVariable" in param_str:
                        in_loc = "path"
                    elif "@RequestHeader" in param_str:
                        in_loc = "header"

                    params.append(EndpointParam(
                        name=p_name,
                        param_type=p_type,
                        in_location=in_loc
                    ))

            # Table references in the whole source
            tables = set()
            for t_match in TABLE_SQL_REGEX.findall(self.code):
                t = t_match.upper()
                if t not in EXCLUDE_TABLES and len(t) > 3:
                    tables.add(t)

            endpoints.append(EndpointInfo(
                http_method=http_method,
                path=full_path,
                class_name=full_class_name,
                method_name=method_name,
                summary=summary or f"{class_name}#{method_name}",
                parameters=params,
                return_type=ret_type,
                permissions=perms,
                tables=list(tables),
                source_type="java"
            ))

        return endpoints
