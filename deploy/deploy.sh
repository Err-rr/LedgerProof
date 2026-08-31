#!/usr/bin/env bash
# Build the Lambda container image, push it to ECR, and create/update the
# Lambda function + HTTP API Gateway in front of it. Idempotent: re-running
# after a code change rebuilds the image, pushes a new tag, and updates the
# existing Lambda function in place (its ARN -- and therefore the API
# Gateway integration pointing at it -- does not change across redeploys).
#
# Required environment variables:
#   DATABASE_URL      Neon Postgres connection string (after `alembic upgrade head`)
#   S3_BUCKET_NAME     bucket to hold uploaded run files (created if missing)
#
# Optional environment variables (sensible defaults shown):
#   AWS_REGION             ap-south-1
#   ECR_REPO_NAME          ledgerproof-api
#   LAMBDA_FUNCTION_NAME   ledgerproof-api
#   LAMBDA_ROLE_NAME       ledgerproof-api-role   (created if missing)
#   API_NAME               ledgerproof-api
#   LAMBDA_MEMORY_MB       1024
#   LAMBDA_TIMEOUT_SECONDS 30
#   IMAGE_TAG              latest
#   ANTHROPIC_API_KEY, RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
#       forwarded to the Lambda's environment if set; the /ask endpoint and
#       agent/resolve.py degrade to a null client when ANTHROPIC_API_KEY is
#       absent, so this is optional for a first deploy.
#
# Known simplification: secrets are passed as plain Lambda environment
# variables, not via Secrets Manager/SSM Parameter Store. Fine for a
# buildathon submission; swap in SSM references before treating this as
# production-hardened.
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-south-1}"
ECR_REPO_NAME="${ECR_REPO_NAME:-ledgerproof-api}"
LAMBDA_FUNCTION_NAME="${LAMBDA_FUNCTION_NAME:-ledgerproof-api}"
LAMBDA_ROLE_NAME="${LAMBDA_ROLE_NAME:-ledgerproof-api-role}"
API_NAME="${API_NAME:-ledgerproof-api}"
LAMBDA_MEMORY_MB="${LAMBDA_MEMORY_MB:-1024}"
LAMBDA_TIMEOUT_SECONDS="${LAMBDA_TIMEOUT_SECONDS:-30}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

: "${DATABASE_URL:?Set DATABASE_URL to your Neon connection string before deploying}"
: "${S3_BUCKET_NAME:?Set S3_BUCKET_NAME to the bucket that will hold uploaded run files}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

command -v aws >/dev/null 2>&1 || { echo "aws CLI is required" >&2; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 1; }

AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${ECR_REGISTRY}/${ECR_REPO_NAME}:${IMAGE_TAG}"

ENV_JSON_FILE="$(mktemp)"
trap 'rm -f "$ENV_JSON_FILE"' EXIT

echo "==> Ensuring S3 bucket ${S3_BUCKET_NAME} exists"
if ! aws s3api head-bucket --bucket "$S3_BUCKET_NAME" 2>/dev/null; then
    if [ "$AWS_REGION" = "us-east-1" ]; then
        aws s3api create-bucket --bucket "$S3_BUCKET_NAME" --region "$AWS_REGION" >/dev/null
    else
        aws s3api create-bucket --bucket "$S3_BUCKET_NAME" --region "$AWS_REGION" \
            --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
    fi
    aws s3api put-public-access-block --bucket "$S3_BUCKET_NAME" \
        --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

echo "==> Ensuring ECR repository ${ECR_REPO_NAME} exists"
aws ecr describe-repositories --repository-names "$ECR_REPO_NAME" --region "$AWS_REGION" >/dev/null 2>&1 || \
    aws ecr create-repository --repository-name "$ECR_REPO_NAME" --region "$AWS_REGION" \
        --image-scanning-configuration scanOnPush=true >/dev/null

echo "==> Building image ${IMAGE_URI} (linux/amd64)"
docker build --platform linux/amd64 -t "$IMAGE_URI" -f "${REPO_ROOT}/Dockerfile" "$REPO_ROOT"

echo "==> Logging in to ECR"
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "$ECR_REGISTRY"

echo "==> Pushing image"
docker push "$IMAGE_URI"

echo "==> Ensuring IAM execution role ${LAMBDA_ROLE_NAME} exists"
if ! aws iam get-role --role-name "$LAMBDA_ROLE_NAME" >/dev/null 2>&1; then
    aws iam create-role --role-name "$LAMBDA_ROLE_NAME" \
        --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
    aws iam attach-role-policy --role-name "$LAMBDA_ROLE_NAME" \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    aws iam put-role-policy --role-name "$LAMBDA_ROLE_NAME" --policy-name ledgerproof-s3-access \
        --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":[\"s3:PutObject\",\"s3:GetObject\"],\"Resource\":\"arn:aws:s3:::${S3_BUCKET_NAME}/*\"}]}"
    echo "    waiting for IAM role to propagate..."
    sleep 10
fi
LAMBDA_ROLE_ARN="$(aws iam get-role --role-name "$LAMBDA_ROLE_NAME" --query 'Role.Arn' --output text)"

# Build the environment JSON via Python rather than AWS CLI shorthand syntax
# ("Variables={K=V,...}") so a DATABASE_URL or key containing a comma,
# equals sign, or brace can never corrupt the CLI's shorthand parser.
python3 - "$ENV_JSON_FILE" <<'PYEOF'
import json
import os
import sys

env = {
    "DATABASE_URL": os.environ["DATABASE_URL"],
    "S3_BUCKET_NAME": os.environ["S3_BUCKET_NAME"],
    "AWS_REGION": os.environ.get("AWS_REGION", "ap-south-1"),
}
for key in ("ANTHROPIC_API_KEY", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"):
    value = os.environ.get(key)
    if value:
        env[key] = value

with open(sys.argv[1], "w", encoding="utf-8") as fh:
    json.dump({"Variables": env}, fh)
PYEOF

echo "==> Creating or updating Lambda function ${LAMBDA_FUNCTION_NAME}"
if aws lambda get-function --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
    aws lambda update-function-code --function-name "$LAMBDA_FUNCTION_NAME" \
        --image-uri "$IMAGE_URI" --region "$AWS_REGION" >/dev/null
    aws lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"
    aws lambda update-function-configuration --function-name "$LAMBDA_FUNCTION_NAME" \
        --environment "file://${ENV_JSON_FILE}" \
        --timeout "$LAMBDA_TIMEOUT_SECONDS" --memory-size "$LAMBDA_MEMORY_MB" \
        --region "$AWS_REGION" >/dev/null
    aws lambda wait function-updated --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"
else
    aws lambda create-function --function-name "$LAMBDA_FUNCTION_NAME" \
        --package-type Image --code ImageUri="$IMAGE_URI" --role "$LAMBDA_ROLE_ARN" \
        --timeout "$LAMBDA_TIMEOUT_SECONDS" --memory-size "$LAMBDA_MEMORY_MB" \
        --environment "file://${ENV_JSON_FILE}" --region "$AWS_REGION" >/dev/null
    aws lambda wait function-active --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION"
fi

LAMBDA_ARN="$(aws lambda get-function --function-name "$LAMBDA_FUNCTION_NAME" --region "$AWS_REGION" \
    --query 'Configuration.FunctionArn' --output text)"

echo "==> Ensuring HTTP API Gateway ${API_NAME} exists, proxying to the Lambda"
API_ID="$(aws apigatewayv2 get-apis --region "$AWS_REGION" \
    --query "Items[?Name=='${API_NAME}'].ApiId" --output text)"
if [ -z "$API_ID" ]; then
    # --target on create-api wires up a Lambda proxy integration, a
    # catch-all $default route, and an auto-deployed $default stage in one call.
    API_ID="$(aws apigatewayv2 create-api --name "$API_NAME" --protocol-type HTTP \
        --target "$LAMBDA_ARN" --region "$AWS_REGION" --query 'ApiId' --output text)"
fi

echo "==> Granting API Gateway permission to invoke the Lambda"
aws lambda add-permission --function-name "$LAMBDA_FUNCTION_NAME" \
    --statement-id apigateway-invoke --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${AWS_REGION}:${AWS_ACCOUNT_ID}:${API_ID}/*/*" \
    --region "$AWS_REGION" >/dev/null 2>&1 || echo "    (permission already granted)"

API_ENDPOINT="$(aws apigatewayv2 get-api --api-id "$API_ID" --region "$AWS_REGION" --query 'ApiEndpoint' --output text)"

echo ""
echo "Deployed."
echo "  Lambda function: $LAMBDA_FUNCTION_NAME"
echo "  Image:           $IMAGE_URI"
echo "  API endpoint:    $API_ENDPOINT"
echo ""
echo "If you have not already, apply the schema before using the API:"
echo "  DATABASE_URL=... python -m alembic upgrade head"
