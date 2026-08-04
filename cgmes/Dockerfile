ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

ARG PYPOWSYBL_VERSION=1.13.0

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY environment/requirements-ci.txt /tmp/requirements-ci.txt
RUN grep -v '^pypowsybl==' /tmp/requirements-ci.txt > /tmp/requirements-ci-base.txt \
    && python -m pip install --no-cache-dir -r /tmp/requirements-ci-base.txt \
    && python -m pip install --no-cache-dir "pypowsybl==${PYPOWSYBL_VERSION}"

ENTRYPOINT ["python"]
CMD ["-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"]
