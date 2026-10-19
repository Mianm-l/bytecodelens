import io
import re
import struct
from typing import Any, Dict, List, Optional, Set, Tuple
from ..models import ClassInfo, EndpointInfo, EndpointParam

TABLE_SQL_REGEX = re.compile(
    r"\b(?:FROM|INTO|UPDATE|JOIN|TABLE)\s+([a-zA-Z0-9_]{3,32})\b",
    re.IGNORECASE
)

EXCLUDE_TABLES = {
    "DUAL", "SET", "VALUES", "WHERE", "SELECT", "NULL", "AND", "OR", "ON", "AS"
}

def parse_java_descriptor(desc: str) -> Tuple[List[str], str]:
    """Parse method descriptor like (Ljava/lang/String;I)Ljava/lang/String;"""
    if not desc or "(" not in desc or ")" not in desc:
        return [], "void"

    params_str = desc[desc.find("(") + 1 : desc.rfind(")")]
    return_str = desc[desc.rfind(")") + 1 :]

    params = []
    i = 0
    while i < len(params_str):
        c = params_str[i]
        if c == 'L':
            end = params_str.find(';', i)
            if end != -1:
                params.append(params_str[i + 1 : end].replace('/', '.'))
                i = end + 1
            else:
                break
        elif c == '[':
            # Array
            i += 1
        elif c in 'ZBCSIFDJ':
            type_map = {'Z': 'boolean', 'B': 'byte', 'C': 'char', 'S': 'short',
                        'I': 'int', 'F': 'float', 'D': 'double', 'J': 'long'}
            params.append(type_map.get(c, 'unknown'))
            i += 1
        else:
            i += 1

    ret_type = "void"
    if return_str.startswith('L'):
        ret_type = return_str[1:-1].replace('/', '.')
    elif return_str and return_str[0] in 'ZBCSIFDJ':
        type_map = {'Z': 'boolean', 'B': 'byte', 'C': 'char', 'S': 'short',
                    'I': 'int', 'F': 'float', 'D': 'double', 'J': 'long'}
        ret_type = type_map.get(return_str[0], 'unknown')

    return params, ret_type

class ClassBytecodeParser:
    """Pure Python JVM Class File Parser."""

    def __init__(self, data: bytes):
        self.stream = io.BytesIO(data)
        self.cp: List[Any] = [None]
        self.class_name = ""
        self.super_class = ""
        self.interfaces: List[str] = []
        self.class_annotations: Dict[str, Any] = {}
        self.methods: List[Dict[str, Any]] = []
        self.sql_tables: Set[str] = set()

    def parse(self) -> None:
        magic = self.stream.read(4)
        if magic != b'\xca\xfe\xba\xbe':
            raise ValueError("Not a valid JVM class file (Magic mismatch)")

        minor, major = struct.unpack(">HH", self.stream.read(4))
        cp_count = struct.unpack(">H", self.stream.read(2))[0]

        # Parse Constant Pool
        i = 1
        while i < cp_count:
            tag = struct.unpack(">B", self.stream.read(1))[0]
            if tag == 1: # Utf8
                length = struct.unpack(">H", self.stream.read(2))[0]
                val = self.stream.read(length).decode("utf-8", errors="replace")
                self.cp.append(("Utf8", val))
                # Check for table names in embedded SQL strings
                if any(k in val.upper() for k in ("SELECT ", "INSERT INTO ", "UPDATE ", "DELETE FROM ")):
                    for match in TABLE_SQL_REGEX.findall(val):
                        tbl = match.upper()
                        if tbl not in EXCLUDE_TABLES and len(tbl) > 3:
                            self.sql_tables.add(tbl)
            elif tag in (3, 4): # Integer, Float
                self.cp.append(("Num", self.stream.read(4)))
            elif tag in (5, 6): # Long, Double
                self.cp.append(("Num2", self.stream.read(8)))
                self.cp.append(None)
                i += 1
            elif tag in (7, 8, 16, 19, 20): # Class, String, MethodType, Module, Package
                idx = struct.unpack(">H", self.stream.read(2))[0]
                self.cp.append(("Ref1", tag, idx))
            elif tag in (9, 10, 11, 12, 17, 18): # Fieldref, Methodref, etc.
                i1, i2 = struct.unpack(">HH", self.stream.read(4))
                self.cp.append(("Ref2", tag, i1, i2))
            elif tag == 15: # MethodHandle
                self.stream.read(3)
                self.cp.append(("MethodHandle",))
            else:
                self.cp.append(("Unknown", tag))
            i += 1

        # Class headers
        flags, this_c, super_c, iface_count = struct.unpack(">HHHH", self.stream.read(8))
        self.class_name = self._resolve_class_name(this_c)
        if super_c > 0:
            self.super_class = self._resolve_class_name(super_c)

        for _ in range(iface_count):
            iface_idx = struct.unpack(">H", self.stream.read(2))[0]
            self.interfaces.append(self._resolve_class_name(iface_idx))

        # Fields
        field_count = struct.unpack(">H", self.stream.read(2))[0]
        for _ in range(field_count):
            self.stream.read(6) # flags, name_idx, desc_idx
            attr_count = struct.unpack(">H", self.stream.read(2))[0]
            for _ in range(attr_count):
                self.stream.read(2) # name_idx
                length = struct.unpack(">I", self.stream.read(4))[0]
                self.stream.read(length)

        # Methods
        method_count = struct.unpack(">H", self.stream.read(2))[0]
        for _ in range(method_count):
            m_flags, m_name_idx, m_desc_idx = struct.unpack(">HHH", self.stream.read(6))
            m_name = self._resolve_utf8(m_name_idx)
            m_desc = self._resolve_utf8(m_desc_idx)
            m_attr_count = struct.unpack(">H", self.stream.read(2))[0]

            m_annotations = {}
            for _ in range(m_attr_count):
                attr_name_idx = struct.unpack(">H", self.stream.read(2))[0]
                attr_len = struct.unpack(">I", self.stream.read(4))[0]
                attr_name = self._resolve_utf8(attr_name_idx)
                if attr_name in ("RuntimeVisibleAnnotations", "RuntimeInvisibleAnnotations"):
                    m_annotations.update(self._parse_annotations())
                else:
                    self.stream.read(attr_len)

            self.methods.append({
                "name": m_name,
                "descriptor": m_desc,
                "flags": m_flags,
                "annotations": m_annotations
            })

        # Class attributes
        class_attr_count = struct.unpack(">H", self.stream.read(2))[0]
        for _ in range(class_attr_count):
            attr_name_idx = struct.unpack(">H", self.stream.read(2))[0]
            attr_len = struct.unpack(">I", self.stream.read(4))[0]
            attr_name = self._resolve_utf8(attr_name_idx)
            if attr_name in ("RuntimeVisibleAnnotations", "RuntimeInvisibleAnnotations"):
                self.class_annotations.update(self._parse_annotations())
            else:
                self.stream.read(attr_len)

    def _resolve_utf8(self, idx: int) -> str:
        if idx > 0 and idx < len(self.cp):
            item = self.cp[idx]
            if item and item[0] == "Utf8":
                return item[1]
        return ""

    def _resolve_class_name(self, idx: int) -> str:
        if idx > 0 and idx < len(self.cp):
            item = self.cp[idx]
            if item and item[0] == "Ref1" and item[1] == 7: # Class
                utf8_idx = item[2]
                return self._resolve_utf8(utf8_idx).replace("/", ".")
        return ""

    def _parse_annotations(self) -> Dict[str, Any]:
        """Parse RuntimeVisibleAnnotations attribute structure."""
        annotations = {}
        try:
            num_ann = struct.unpack(">H", self.stream.read(2))[0]
            for _ in range(num_ann):
                type_idx = struct.unpack(">H", self.stream.read(2))[0]
                ann_type = self._resolve_utf8(type_idx)
                num_pairs = struct.unpack(">H", self.stream.read(2))[0]
                pairs = {}
                for _ in range(num_pairs):
                    name_idx = struct.unpack(">H", self.stream.read(2))[0]
                    pair_name = self._resolve_utf8(name_idx)
                    pair_val = self._parse_element_value()
                    pairs[pair_name] = pair_val
                # Clean up type: Lorg/springframework/...; -> org.springframework...
                clean_type = ann_type.strip('L;').replace('/', '.')
                annotations[clean_type] = pairs
        except Exception:
            pass
        return annotations

    def _parse_element_value(self) -> Any:
        tag = self.stream.read(1).decode("latin1", errors="ignore")
        if tag in 'sBCDFIJSZ':
            const_idx = struct.unpack(">H", self.stream.read(2))[0]
            return self._resolve_utf8(const_idx)
        elif tag == 'e': # enum
            self.stream.read(2)
            val_idx = struct.unpack(">H", self.stream.read(2))[0]
            return self._resolve_utf8(val_idx)
        elif tag == 'c': # class
            class_idx = struct.unpack(">H", self.stream.read(2))[0]
            return self._resolve_utf8(class_idx)
        elif tag == '@': # annotation
            self.stream.read(2)
            num_pairs = struct.unpack(">H", self.stream.read(2))[0]
            sub = {}
            for _ in range(num_pairs):
                name_idx = struct.unpack(">H", self.stream.read(2))[0]
                sub[self._resolve_utf8(name_idx)] = self._parse_element_value()
            return sub
        elif tag == '[': # array
            num_values = struct.unpack(">H", self.stream.read(2))[0]
            return [self._parse_element_value() for _ in range(num_values)]
        return None

    def extract_endpoints(self) -> List[EndpointInfo]:
        """Extract REST endpoints from Spring / RuoYi annotations."""
        endpoints = []
        is_controller = False
        base_path = ""

        # Check class annotations
        for ann, vals in self.class_annotations.items():
            if any(k in ann for k in ("RestController", "Controller", "SeeyonController")):
                is_controller = True
            if "RequestMapping" in ann:
                is_controller = True
                path_val = vals.get("value") or vals.get("path") or ""
                if isinstance(path_val, list) and path_val:
                    base_path = str(path_val[0])
                elif isinstance(path_val, str):
                    base_path = path_val

        if not is_controller:
            return []

        if base_path and not base_path.startswith('/'):
            base_path = '/' + base_path
        if base_path.endswith('/'):
            base_path = base_path[:-1]

        # Scan methods
        for m in self.methods:
            m_name = m["name"]
            m_desc = m["descriptor"]
            m_ann = m["annotations"]

            http_method = None
            m_path = ""
            perms = []

            for ann, vals in m_ann.items():
                if "GetMapping" in ann:
                    http_method = "GET"
                    val = vals.get("value") or vals.get("path") or ""
                    m_path = val[0] if isinstance(val, list) and val else str(val)
                elif "PostMapping" in ann:
                    http_method = "POST"
                    val = vals.get("value") or vals.get("path") or ""
                    m_path = val[0] if isinstance(val, list) and val else str(val)
                elif "PutMapping" in ann:
                    http_method = "PUT"
                    val = vals.get("value") or vals.get("path") or ""
                    m_path = val[0] if isinstance(val, list) and val else str(val)
                elif "DeleteMapping" in ann:
                    http_method = "DELETE"
                    val = vals.get("value") or vals.get("path") or ""
                    m_path = val[0] if isinstance(val, list) and val else str(val)
                elif "RequestMapping" in ann:
                    http_method = "POST" if "method" not in vals else str(vals.get("method"))
                    val = vals.get("value") or vals.get("path") or ""
                    m_path = val[0] if isinstance(val, list) and val else str(val)

                # Permissions
                if "PreAuthorize" in ann or "RequiresPermissions" in ann:
                    raw_perm = str(vals.get("value", ""))
                    # Extract string inside quotes
                    found = re.findall(r"['\"]([^'\"]+)['\"]", raw_perm)
                    if found:
                        perms.extend(found)
                    else:
                        perms.append(raw_perm)

            if http_method:
                if m_path and not m_path.startswith('/'):
                    m_path = '/' + m_path
                full_path = f"{base_path}{m_path}" or "/"

                param_types, ret_type = parse_java_descriptor(m_desc)
                params = [
                    EndpointParam(
                        name=f"arg{idx}",
                        param_type=pt,
                        in_location="body" if http_method in ("POST", "PUT") and idx == 0 else "query"
                    )
                    for idx, pt in enumerate(param_types)
                ]

                endpoints.append(EndpointInfo(
                    http_method=http_method,
                    path=full_path,
                    class_name=self.class_name,
                    method_name=m_name,
                    summary=f"Auto-extracted from {self.class_name}#{m_name}",
                    parameters=params,
                    return_type=ret_type,
                    permissions=perms,
                    tables=list(self.sql_tables),
                    source_type="class"
                ))

        return endpoints
