from scripts.operator import recover_v3_runtime_contract as recovery


def test_structured_mapping_keys_support_hyphens_and_dots():
    assert "sensitive-environment-assignment" in recovery._scan_text(
        "api-key: opaque-test-key\n", "config.yml"
    )
    assert "sensitive-environment-assignment" in recovery._scan_text(
        "spring.datasource.password: opaque-test-password\n", "config.yml"
    )


def test_flow_style_structured_environment_entry_is_scanned():
    findings = recovery._scan_text(
        "env: [{name: POSTGRES_PASSWORD, value: opaque-test-password}]\n",
        "deployment.yml",
    )
    assert "sensitive-environment-assignment" in findings


def test_pwd_suffix_is_sensitive_but_shell_pwd_is_not():
    assert "sensitive-environment-assignment" in recovery._scan_text(
        "DB_PWD=opaque-test-password\n", "start.sh"
    )
    assert recovery._scan_text('PWD="$(pwd)"\n', "start.sh") == ()


def test_space_separated_credential_options_are_scanned():
    assert "credential-command-option" in recovery._scan_text(
        "client --password opaque-test-password\n", "start.sh"
    )
    assert "credential-command-option" in recovery._scan_text(
        'command: ["client", "--password", "opaque-test-password"]\n',
        "compose.yml",
    )
    assert recovery._scan_text(
        "client --password ${DB_PASSWORD}\n", "start.sh"
    ) == ()


def test_kubernetes_secret_payload_is_excluded_regardless_of_key_name():
    findings = recovery._scan_text(
        "apiVersion: v1\nkind: Secret\ndata:\n  auth: b3BhcXVlLXRlc3QtdmFsdWU=\n",
        "secret.yml",
    )
    assert "kubernetes-secret-payload" in findings


def test_python_ast_distinguishes_runtime_lookup_from_literal_assignment():
    assert recovery._scan_text(
        'import os\nINARA_API_KEY = os.getenv("INARA_API_KEY")\n',
        "inara_api.py",
    ) == ()
    assert "sensitive-environment-assignment" in recovery._scan_text(
        'INARA_API_KEY = "opaque-test-key"\n',
        "inara_api.py",
    )
    assert "sensitive-environment-assignment" in recovery._scan_text(
        'import os\nINARA_API_KEY = os.getenv("INARA_API_KEY", "opaque-default")\n',
        "inara_api.py",
    )
