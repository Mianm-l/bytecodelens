import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.models import EndpointInfo, ProjectScanResult
from src.parsers.class_parser import ClassBytecodeParser
from src.parsers.source_parser import JavaSourceParser
from src.parsers.mybatis_parser import MyBatisParser
from src.parsers.scanner import TargetScanner
from src.exporters.openapi_exporter import OpenAPIExporter
from src.exporters.markdown_exporter import MarkdownExporter

SAMPLE_CONTROLLER = """package cn.iocoder.yudao.module.procurement.controller;

import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

/**
 * 采购订单协同管理接口
 */
@RestController
@RequestMapping("/api/procurement/order")
public class PurchaseOrderController {

    /**
     * 分页查询采购单列表
     */
    @GetMapping("/page")
    @PreAuthorize("hasAuthority('procurement:order:query')")
    public CommonResult<PageResult<OrderVO>> getOrderPage(@RequestParam String orderId) {
        String query = "SELECT * FROM CT_PURCHASE_ORDER WHERE ORDER_ID = ?";
        return null;
    }

    /**
     * 审核通过并生效采购单
     */
    @PostMapping("/approve")
    @PreAuthorize("hasAuthority('procurement:order:approve')")
    public CommonResult<Boolean> approveOrder(@RequestParam Long id) {
        String update = "UPDATE CT_PURCHASE_ORDER SET ORDER_STATUS = 2 WHERE ID = ?";
        return null;
    }
}
"""

SAMPLE_MYBATIS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="cn.iocoder.yudao.module.procurement.mapper.ReceivingBillMapper">
    <select id="selectByOrderId" resultType="ReceivingBillDO">
        SELECT * FROM CT_RECEIVING_BILL WHERE REF_ORDER_ID = #{orderId}
    </select>
    <insert id="insert">
        INSERT INTO CT_RECEIVING_BILL (RECEIVE_ID, ACTUAL_AMOUNT) VALUES (#{receiveId}, #{actualAmount})
    </insert>
</mapper>
"""

class TestBytecodeLens(unittest.TestCase):
    def test_java_source_parser(self):
        """Test parsing Spring Controller Java source code."""
        parser = JavaSourceParser(SAMPLE_CONTROLLER)
        endpoints = parser.parse()

        self.assertEqual(len(endpoints), 2)

        ep1 = endpoints[0]
        self.assertEqual(ep1.http_method, "GET")
        self.assertEqual(ep1.path, "/api/procurement/order/page")
        self.assertEqual(ep1.summary, "分页查询采购单列表")
        self.assertIn("procurement:order:query", ep1.permissions)
        self.assertIn("CT_PURCHASE_ORDER", ep1.tables)

        ep2 = endpoints[1]
        self.assertEqual(ep2.http_method, "POST")
        self.assertEqual(ep2.path, "/api/procurement/order/approve")
        self.assertIn("procurement:order:approve", ep2.permissions)

    def test_mybatis_parser(self):
        """Test parsing MyBatis Mapper XML."""
        parser = MyBatisParser(SAMPLE_MYBATIS_XML)
        tables = parser.parse()

        self.assertIn("CT_RECEIVING_BILL", tables)
        usage = tables["CT_RECEIVING_BILL"]
        self.assertIn("SELECT", usage.operations)
        self.assertIn("INSERT", usage.operations)
        self.assertIn("ReceivingBillMapper", usage.mapper_id)

    def test_real_class_bytecode_parser(self):
        """Test parsing actual Java bytecode .class file from disk if present."""
        scratch_dir = BASE_DIR.parent
        class_file = scratch_dir / "tmp_vo.class"
        if class_file.exists():
            with open(class_file, "rb") as f:
                parser = ClassBytecodeParser(f.read())
                parser.parse()
                self.assertEqual(parser.class_name, "nc.impl.pbm.budgetadd.ProjectBudgetAddQueryImpl")
                self.assertTrue(len(parser.methods) > 0)

    def test_exporters(self):
        """Test OpenAPI and Markdown spec generation."""
        parser = JavaSourceParser(SAMPLE_CONTROLLER)
        endpoints = parser.parse()
        m_parser = MyBatisParser(SAMPLE_MYBATIS_XML)
        tables = m_parser.parse()

        res = ProjectScanResult(
            target_path="/test/path",
            scan_mode="source",
            total_classes=2,
            total_endpoints=len(endpoints),
            total_tables=len(tables),
            endpoints=endpoints,
            tables=tables
        )

        # OpenAPI Export
        openapi = OpenAPIExporter.to_openapi(res)
        self.assertEqual(openapi["openapi"], "3.0.0")
        self.assertIn("/api/procurement/order/page", openapi["paths"])
        self.assertIn("get", openapi["paths"]["/api/procurement/order/page"])

        # Markdown Export
        md = MarkdownExporter.to_markdown(res)
        self.assertIn("mermaid", md)
        self.assertIn("CT_PURCHASE_ORDER", md)
        self.assertIn("/api/procurement/order/approve", md)

    def test_target_scanner_directory(self):
        """Test scanning a directory with Java source and XML files."""
        temp_dir = tempfile.mkdtemp()
        try:
            # Create dummy java file
            java_path = Path(temp_dir) / "PurchaseOrderController.java"
            with open(java_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_CONTROLLER)

            # Create dummy mapper xml
            xml_path = Path(temp_dir) / "ReceivingBillMapper.xml"
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(SAMPLE_MYBATIS_XML)

            scanner = TargetScanner(temp_dir)
            result = scanner.scan()

            self.assertEqual(result.total_endpoints, 2)
            self.assertTrue(result.total_tables >= 2)
            self.assertEqual(result.scan_mode, "hybrid")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
