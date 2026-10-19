from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class EndpointParam(BaseModel):
    name: str
    param_type: str = "string"
    required: bool = True
    in_location: str = "query" # "query", "path", "body", "header"
    description: Optional[str] = None

class EndpointInfo(BaseModel):
    http_method: str = "GET"
    path: str
    class_name: str
    method_name: str
    summary: Optional[str] = None
    parameters: List[EndpointParam] = Field(default_factory=list)
    return_type: str = "java.lang.Object"
    permissions: List[str] = Field(default_factory=list)
    tables: List[str] = Field(default_factory=list)
    source_type: str = "class" # "class" or "java"

class ClassInfo(BaseModel):
    class_name: str
    package_name: str = ""
    super_class: Optional[str] = None
    interfaces: List[str] = Field(default_factory=list)
    base_path: str = ""
    is_controller: bool = False
    methods: List[str] = Field(default_factory=list)

class TableUsage(BaseModel):
    table_name: str
    operations: List[str] = Field(default_factory=list) # SELECT, INSERT, UPDATE, DELETE
    mapper_id: Optional[str] = None
    referenced_by_endpoints: List[str] = Field(default_factory=list)

class ProjectScanResult(BaseModel):
    target_path: str
    scan_mode: str = "bytecode" # "bytecode", "source", "hybrid"
    total_classes: int = 0
    total_endpoints: int = 0
    total_tables: int = 0
    endpoints: List[EndpointInfo] = Field(default_factory=list)
    tables: Dict[str, TableUsage] = Field(default_factory=dict)
