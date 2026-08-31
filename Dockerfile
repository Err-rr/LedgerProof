# Lambda container image for the LedgerProof API (FastAPI + Mangum).
# Built on AWS's own Lambda base image so the Lambda runtime interface
# client is already wired up -- CMD names the Mangum handler directly.
#
# pandas/pyarrow/numpy/psycopg[binary] are why this is a container image
# and not a zip layer: they exceed the 250MB unzipped zip-layer limit.
FROM public.ecr.aws/lambda/python:3.11

WORKDIR ${LAMBDA_TASK_ROOT}

# Only what's needed to install the package and run the API. alembic/ is
# deliberately excluded from the runtime image -- migrations are run once,
# out-of-band, via `alembic upgrade head` from a developer machine or a CI
# job against DATABASE_URL, never from inside the Lambda itself.
COPY pyproject.toml README.md ./
COPY api ./api
COPY core ./core
COPY agent ./agent

RUN pip install --no-cache-dir .

CMD ["api.main.handler"]
