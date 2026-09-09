SELECT assembly_id, program_id, system_name, readiness_pct, updated_at FROM `dc-synthetic-demo.analytics_governed.assembly_readiness_v1` WHERE program_id = @program_id ORDER BY assembly_id;
