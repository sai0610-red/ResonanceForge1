"""Shape checks for deploy/aws templates (nothing here talks to AWS)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
AWS = ROOT / "deploy" / "aws"
VARS = {
    "AWS_ACCOUNT_ID": "123456789012",
    "AWS_REGION": "us-west-2",
    "IMAGE_TAG": "abc123",
    "LLM_PROVIDER": "bedrock",
    "EFS_FILE_SYSTEM_ID": "fs-123",
    "EFS_ACCESS_POINT_ID": "fsap-123",
    "DEMO_TOKEN_SECRET_ARN": "arn:aws:secretsmanager:us-west-2:123456789012:secret:rf/demo-AbC",
    "GROQ_SECRET_ARN": "arn:aws:secretsmanager:us-west-2:123456789012:secret:rf/groq-DeF",
}


def _render(path: Path) -> dict:
    raw = path.read_text()
    used = set(re.findall(r"\$\{([A-Z_]+)\}", raw))
    assert used <= set(VARS), f"undocumented placeholders: {used - set(VARS)}"
    return json.loads(Template(raw).substitute(VARS))


def test_all_templates_render_to_json():
    files = list(AWS.rglob("*.json"))
    assert len(files) >= 4
    for f in files:
        _render(f)


def test_task_definition_essentials():
    td = _render(AWS / "task-definition.json")
    assert td["requiresCompatibilities"] == ["FARGATE"] and td["networkMode"] == "awsvpc"
    (c,) = td["containerDefinitions"]
    env = {e["name"]: e["value"] for e in c["environment"]}
    secrets = {s["name"]: s["valueFrom"] for s in c["secrets"]}
    # Secrets come only from Secrets Manager, never plain environment.
    assert {"DEMO_TOKEN", "GROQ_API_KEY"} <= set(secrets)
    assert all(v.startswith("arn:aws:secretsmanager:") for v in secrets.values())
    assert not {"DEMO_TOKEN", "GROQ_API_KEY", "AWS_SECRET_ACCESS_KEY"} & set(env)
    assert env["ENV"] == "production" and env["LLM_PROVIDER"] == "bedrock"
    assert env["TRUSTED_PROXY"] == "true" and env["TRUSTED_PROXY_HOP"] == "last"
    assert env["DATA_DIR"] == "/app/data"
    assert c["portMappings"][0]["containerPort"] == 8000
    assert "/health" in " ".join(c["healthCheck"]["command"])
    assert c["logConfiguration"]["logDriver"] == "awslogs"
    assert c["logConfiguration"]["options"]["awslogs-group"] == "/ecs/resonanceforge"
    assert c["mountPoints"][0]["containerPath"] == "/app/data"
    assert td["volumes"][0]["efsVolumeConfiguration"]["transitEncryption"] == "ENABLED"


def test_task_role_scoped_to_configured_model():
    td = _render(AWS / "task-definition.json")
    env = {e["name"]: e["value"] for e in td["containerDefinitions"][0]["environment"]}
    policy = _render(AWS / "iam" / "task-role-policy.json")
    bedrock = next(s for s in policy["Statement"] if "bedrock:InvokeModel" in s["Action"])
    assert bedrock["Resource"].endswith("foundation-model/" + env["BEDROCK_MODEL_ID"])
    assert "*" not in bedrock["Resource"]


def test_docs_say_not_deployed():
    text = (ROOT / "docs" / "deploy-aws.md").read_text()
    assert "not deployed" in text.lower()
