# deploy/aws

Templates for running ResonanceForge on ECS Fargate behind an ALB. **Not deployed
from this repo and not tested against a live AWS account.** Step-by-step commands
are in [docs/deploy-aws.md](../../docs/deploy-aws.md).

| File | What it is |
|------|------------|
| `task-definition.json` | Fargate task: the repo's Dockerfile image from ECR, secrets from Secrets Manager, CloudWatch Logs (`awslogs`), container health check on `/health`, and an EFS volume at `/app/data` |
| `iam/ecs-tasks-trust-policy.json` | Trust policy for both roles |
| `iam/execution-role-secrets-policy.json` | Lets ECS read the two secrets at task start |
| `iam/task-role-policy.json` | Lets the app call the configured Bedrock model and mount the EFS access point |

`${VARS}` are placeholders. Render them with `envsubst` (from gettext), as shown in the guide.
