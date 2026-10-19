from typing import Any, Dict
from ..models import ProjectScanResult

class OpenAPIExporter:
    @staticmethod
    def to_openapi(result: ProjectScanResult, title: str = "Extracted Legacy Java API Spec") -> Dict[str, Any]:
        paths_obj: Dict[str, Any] = {}

        for ep in result.endpoints:
            p = ep.path
            if p not in paths_obj:
                paths_obj[p] = {}

            method_lower = ep.http_method.lower()
            if method_lower == "any":
                method_lower = "post"

            params_list = []
            req_body = None

            for param in ep.parameters:
                if param.in_location == "body":
                    req_body = {
                        "description": f"Request body object: {param.name} ({param.param_type})",
                        "required": param.required,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "description": param.param_type
                                }
                            }
                        }
                    }
                else:
                    params_list.append({
                        "name": param.name,
                        "in": param.in_location,
                        "required": param.required,
                        "schema": {
                            "type": "string" if param.param_type in ("String", "java.lang.String") else "integer" if param.param_type in ("int", "Integer", "long", "Long") else "string"
                        }
                    })

            operation_obj: Dict[str, Any] = {
                "tags": [ep.class_name.split(".")[-1]],
                "summary": ep.summary or f"{ep.class_name}#{ep.method_name}",
                "operationId": f"{ep.class_name}_{ep.method_name}",
                "parameters": params_list,
                "responses": {
                    "200": {
                        "description": f"Successful response returning {ep.return_type}",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "description": ep.return_type
                                }
                            }
                        }
                    }
                },
                "x-java-class": ep.class_name,
                "x-java-method": ep.method_name,
                "x-permissions": ep.permissions,
                "x-referenced-tables": ep.tables
            }

            if req_body:
                operation_obj["requestBody"] = req_body

            paths_obj[p][method_lower] = operation_obj

        return {
            "openapi": "3.0.0",
            "info": {
                "title": title,
                "version": "1.0.0",
                "description": f"Reverse-engineered by Bytecode-Lens from: {result.target_path}. Total endpoints: {result.total_endpoints}, Total tables: {result.total_tables}"
            },
            "paths": paths_obj
        }
