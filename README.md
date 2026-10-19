# Bytecode-Lens (字节码透镜)

> **面向老旧 Java 系统 (Jar / War / Class / 源码) 的零依赖接口契约与数据库表调用链路逆向工程工具**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](requirements.txt)
[![CI](https://github.com/Mianm-l/bytecodelens/actions/workflows/ci.yml/badge.svg)](https://github.com/Mianm-l/bytecodelens/actions)

---

## 🌟 为什么需要 Bytecode-Lens？

在企业级研发与老旧系统维护（如致远协同 OA 插件、用友 NC/NCC 补丁、若依/芋道二次开发及 Spring MVC 历史工程）中，开发者经常面临以下痛点：

1. **接口文档严重缺失或过时**：接手系统只有一堆 `.jar` 包或杂乱源码，找不到完整的 API 清单与入参定义；
2. **重度依赖本地 JDK / 反编译器**：很多反编译工具（如 CFR、Fernflower、Javap）需要本地预装完整 JVM 环境，运行缓慢且无法批量抽取结构化元数据；
3. **改动影响面如盲盒**：修改或重构一个接口时，完全不知道它最终读写了底层哪几张数据库表。

**Bytecode-Lens** 是一个**纯 Python 实现、零 JDK 运行时依赖**的静态逆向分析工具与 MCP 开发者智能体。它直接解析 JVMS Class 字节码常数池、Spring 注解与 MyBatis XML 映射，秒级导出标准 **OpenAPI 3.0.0** 契约及**接口-数据库表影响面拓扑图**。

---

## ✨ 核心特性

- 🚀 **纯 Python JVMS 字节码解析器（Zero JDK Dependency）**：无需在本地或服务器安装 JDK / JRE / javap，直接通过 Python 读取字节码；
- 📦 **双模态扫描支持**：既支持穿透扫描 `.jar`、`.war`、`.class` 二进制归档，也支持递归扫描 `.java` 源码树与 Javadoc 注释；
- 🔗 **全链路穿透（Controller -> Service -> Mapper -> DB Tables）**：智能识别 MyBatis XML 与注解 SQL，自动输出“哪些 API 读写了哪张表”；
- 🔒 **权限矩阵自动提取**：自动提取 Spring Security (`@PreAuthorize`) 与 Shiro (`@RequiresPermissions`) 权限控制标识；
- 📄 **多格式契约导出**：一键生成标准 OpenAPI 3.0.0 (Swagger) 规范与带有 Mermaid 拓扑图的 Markdown 活文档；
- 🤖 **内置 FastMCP 智能体服务器**：可直接挂载到 Cursor、Antigravity、Windsurf 等 AI IDE 作为 MCP Tool，让 AI 拥有老系统架构透视眼。

---

## 🚀 快速上手

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 命令行一键逆向分析 (CLI)

```bash
# 生成包含 Mermaid 拓扑图的 Markdown 接口文档
python -m src.cli /path/to/legacy-system.jar --format markdown -o api-spec.md

# 导出标准 OpenAPI 3.0 JSON 契约
python -m src.cli /path/to/java-project-dir --format openapi -o openapi.json
```

---

## 🔌 配置为 AI IDE 的 MCP Server

在 Cursor / Antigravity / Claude Desktop 等客户端的 MCP 配置文件（如 `mcp_settings.json`）中添加：

```json
{
  "mcpServers": {
    "bytecodelens": {
      "command": "python",
      "args": ["-m", "src.server", "--transport", "stdio"],
      "cwd": "/path/to/bytecodelens"
    }
  }
}
```

### 暴露给 Agent 的核心 MCP Tools

| Tool 原语 | 功能描述 | 典型交互 Prompt 示例 |
| :--- | :--- | :--- |
| `scan_java_target` | 扫描指定的 Jar 文件或 Java 源码工程目录 | *"帮我扫描 /opt/pbm-budget.jar，看看里面有哪些模块和接口"* |
| `list_endpoints` | 按请求方式、模块或关键字检索 API 路由清单 | *"查询所有带有 budget 关键词的 POST 接口清单"* |
| `get_endpoint_detail` | 查看具体路由的完整入参、返回类型与涉及数据库表 | *"查看 /api/procurement/order/page 接口的详细定义"* |
| `find_table_usage` | **逆向影响面分析**：查询特定数据库表被哪些 API 读写 | *"查一下 CT_PURCHASE_ORDER 这张表被哪些接口调用了？"* |
| `export_spec` | 全量导出为 OpenAPI 3.0 规范或 Markdown 拓扑报告 | *"将当前分析结果全量导出为 OpenAPI JSON 契约"* |

---

## 🧪 自动化测试

```bash
python -m unittest tests/test_bytecodelens.py
```

---

## 📄 开源许可证

本项目基于 [Apache 2.0](LICENSE) 协议开源。
