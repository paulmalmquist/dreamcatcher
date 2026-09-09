SELECT po_line_id, program_id, supplier_alias, days_late, updated_at FROM `dc-synthetic-demo.analytics_governed.supplier_delivery_v1` WHERE program_id = @program_id ORDER BY po_line_id;
