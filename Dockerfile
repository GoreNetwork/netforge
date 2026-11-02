# One codebase, one image target per role. A new engine that needs its own
# tooling (for example Terraform) adds a target here rather than growing `worker`.
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app/src
WORKDIR /app
RUN useradd --uid 10001 --create-home netforge
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r requirements/base.txt
COPY src/ src/
COPY automations/ automations/

FROM base AS api
COPY alembic.ini .
USER netforge
EXPOSE 8080
CMD ["uvicorn", "netforge.api.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM base AS worker
ENV ANSIBLE_CONFIG=/app/automations/ansible/ansible.cfg \
    ANSIBLE_COLLECTIONS_PATH=/usr/share/ansible/collections
RUN pip install --no-cache-dir -r requirements/worker.txt \
    && ansible-galaxy collection install \
         -r automations/ansible/requirements.yml \
         -p /usr/share/ansible/collections
USER netforge
CMD ["python", "-m", "netforge.worker.main"]

FROM worker AS test
USER root
RUN pip install --no-cache-dir -r requirements/test.txt
COPY tests/ tests/
USER netforge
CMD ["pytest", "-q", "tests"]
