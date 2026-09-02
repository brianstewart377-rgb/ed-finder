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


def test_python_wrapped_literal_credentials_are_scanned():
    assert "sensitive-environment-assignment" in recovery._scan_text(
        'POSTGRES_PASSWORD = SecretStr("opaque-test-secret")\n',
        "settings.py",
    )
    assert "sensitive-environment-assignment" in recovery._scan_text(
        'POSTGRES_PASSWORD = "opaque-test-secret".strip()\n',
        "settings.py",
    )
    assert recovery._scan_text(
        'import os\nPOSTGRES_PASSWORD = SecretStr(os.getenv("POSTGRES_PASSWORD"))\n',
        "settings.py",
    ) == ()


def test_python_composed_literal_credentials_fail_closed():
    assert "sensitive-environment-assignment" in recovery._scan_text(
        'POSTGRES_PASSWORD = "opaque-" + "test-secret"\n',
        "settings.py",
    )
    assert recovery._scan_text(
        'POSTGRES_PASSWORD = password_reference\n',
        "settings.py",
    ) == ()


def test_python_comments_and_docstrings_are_scanned_for_literal_credentials():
    assert "sensitive-environment-assignment" in recovery._scan_text(
        '# POSTGRES_PASSWORD = "opaque-test-secret"\n',
        "settings.py",
    )
    assert "sensitive-environment-assignment" in recovery._scan_text(
        '"""POSTGRES_PASSWORD = "opaque-test-secret"\n"""\n',
        "settings.py",
    )
    assert recovery._scan_text(
        '# POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")\n',
        "settings.py",
    ) == ()


def test_yaml_sequence_item_sensitive_mapping_key_is_scanned():
    findings = recovery._scan_text(
        "users:\n  - password: opaque-test-secret\n",
        "users.yml",
    )
    assert "sensitive-environment-assignment" in findings


def test_embedded_sql_password_statements_are_scanned_in_non_sql_files():
    assert "sql-password-statement" in recovery._scan_text(
        'psql -c "ALTER ROLE app PASSWORD \'opaque-test-secret\';"\n',
        "rotate.sh",
    )
    assert recovery._scan_text(
        'psql -c "ALTER ROLE app PASSWORD \'${DB_PASSWORD}\';"\n',
        "rotate.sh",
    ) == ()


def test_python_sensitive_keyword_arguments_and_defaults_are_scanned():
    assert "sensitive-environment-assignment" in recovery._scan_text(
        'client.login(password="opaque-test-secret")\n', "client.py"
    )
    assert "sensitive-environment-assignment" in recovery._scan_text(
        'def connect(password="opaque-test-secret"):\n    pass\n', "client.py"
    )
    assert recovery._scan_text(
        'import os\nclient.login(password=os.getenv("DB_PASSWORD"))\n', "client.py"
    ) == ()
    assert recovery._scan_text(
        'def connect(password=None):\n    pass\n', "client.py"
    ) == ()


def test_nested_json_kubernetes_secret_is_scanned():
    findings = recovery._scan_text(
        '{"kind":"List","items":[{"kind":"Secret","data":{"auth":"b3BhcXVl"}}]}',
        "resources.json",
    )
    assert "kubernetes-secret-payload" in findings


def test_credential_named_assignments_are_sensitive_but_path_indirection_is_safe():
    assert "sensitive-environment-assignment" in recovery._scan_text(
        "DB_CREDENTIAL=opaque-test-secret\n", "start.sh"
    )
    assert "sensitive-environment-assignment" in recovery._scan_text(
        "service_credentials: opaque-test-secret\n", "config.yml"
    )
    assert recovery._scan_text(
        "CREDENTIALS_FILE=/run/secrets/service_credentials\n", "start.sh"
    ) == ()


def test_python_prefixed_authorization_strings_are_scanned_without_blocking_dynamic_fstrings():
    assert "authorization-credential" in recovery._scan_text(
        'headers = {"Authorization": u"Bearer opaque-test-credential"}\n', "client.py"
    )
    assert "authorization-credential" in recovery._scan_text(
        'headers = {"Authorization": f"Bearer opaque-test-credential"}\n', "client.py"
    )
    assert recovery._scan_text(
        'headers = {"Authorization": f"Bearer {token}"}\n', "client.py"
    ) == ()


def test_python_byte_string_credentials_are_scanned():
    assert "sensitive-environment-assignment" in recovery._scan_text(
        'API_KEY = b"opaque-test-key"\n', "settings.py"
    )


def test_postgres_escape_string_password_is_scanned():
    assert "sql-password-statement" in recovery._scan_text(
        "ALTER ROLE app PASSWORD E'opaque-test-secret';\n", "rotate.sql"
    )


def test_docker_registry_auth_payload_is_scanned():
    assert "docker-registry-auth" in recovery._scan_text(
        '{"auths":{"registry.example":{"auth":"dXNlcjpwYXNz"}}}',
        ".docker/config.json",
    )
    assert recovery._scan_text(
        '{"auths":{"registry.example":{"auth":"${DOCKER_AUTH}"}}}',
        ".docker/config.json",
    ) == ()


def test_private_jwks_are_scanned_but_public_jwks_are_allowed():
    assert "private-jwk-material" in recovery._scan_text(
        '{"kty":"RSA","n":"n","e":"AQAB","d":"opaque-private"}',
        "jwks.json",
    )
    assert recovery._scan_text(
        '{"kty":"RSA","n":"n","e":"AQAB"}',
        "jwks.json",
    ) == ()
    assert "private-jwk-material" in recovery._scan_text(
        "kty: RSA\nn: n\ne: AQAB\nd: opaque-private\n",
        "jwk.yml",
    )


def test_utf8_bom_does_not_hide_first_yaml_sensitive_key():
    assert "sensitive-environment-assignment" in recovery._scan_text(
        "\ufeffpassword: opaque-test-secret\n", "config.yml"
    )
