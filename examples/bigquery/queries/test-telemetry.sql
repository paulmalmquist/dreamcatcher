SELECT test_run_id, program_id, test_family, pass_rate, updated_at FROM `dc-synthetic-demo.analytics_governed.test_telemetry_v1` WHERE program_id = @program_id ORDER BY test_run_id;
