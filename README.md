# Netforge

Self-service automation for network and server gear. People fill in a form or
call the API, the request is recorded and queued, and a worker runs it with
Ansible, Python or another engine you add. Nautobot is the source of truth for
inventory and IPAM.

```
GUI / REST API ──► Postgres (task record, status queued)
                       │
                       └─► Redis queue, one per engine
                               │
                               ▼
                        Worker claims the task (status running)
                               │  ansible-playbook / python / your engine
                               ▼
                        Nautobot and your gear
                               │
                               ▼
                        Status, log and result saved to Postgres
```

## Quickstart

Requires Docker Desktop (or any Docker engine with Compose v2) and Python 3.

```bash
python scripts/init-env.py
docker compose up -d --wait --wait-timeout 600
python scripts/smoke-test.py
```

The first start takes a few minutes while Nautobot runs its migrations.
`smoke-test.py` makes real reservations, labelled `smoke-<timestamp>`, and leaves
them in Nautobot.

| Service | URL | Sign-in |
|---|---|---|
| Netforge GUI | http://localhost:8080 | None; bound to localhost |
| API docs | http://localhost:8080/api/docs | Bearer token: `NETFORGE_API_TOKEN` in `.env` |
| Nautobot | http://localhost:8081 | `admin` / `NAUTOBOT_SUPERUSER_PASSWORD` in `.env` |

## API

```bash
curl -X POST http://localhost:8080/api/v1/tasks \
  -H "Authorization: Bearer $NETFORGE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_type": "build_new_device", "variables": {"device_name": "core-sw-01"}}'
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/task-types` | Available tasks and their variables |
| POST | `/api/v1/tasks` | Submit a task |
| GET | `/api/v1/tasks` | List tasks; filter with `?status=` and `?limit=` |
| GET | `/api/v1/tasks/{id}` | Status and result |
| GET | `/api/v1/tasks/{id}/logs` | Log lines; use `?after=<line id>` to follow |

## Adding a task

Create `automations/tasks/<name>/` with a `task.yml` and whatever it runs. The
GUI form and API validation are generated from `task.yml`, and the folder is
mounted into the containers, so the task appears without a rebuild or restart.

```yaml
title: Shown in the GUI
description: One line about what it does.
engine: ansible            # or python, or any registered engine
entrypoint: playbook.yml   # relative to this folder
timeout_seconds: 600
variables:
  - name: device_name
    label: Device name
    pattern: "[a-z0-9-]+"  # full match
    pattern_error: can only contain lowercase letters, numbers and dashes
  - name: vlan
    label: VLAN
    type: integer          # string (default), integer or choice
    min: 1
    max: 4094
  - name: site
    label: Site
    type: choice
    choices: [dal1, nyc2]
```

Always use `pattern` on free-text variables. Your playbook or script receives
this text as data, but anything it builds from that text, such as a shell command
or device config, is only as safe as the validation.

## The engine contract

All engines work the same way, which is what keeps them interchangeable. The
child process runs from the task's folder and gets:

| Variable | Meaning |
|---|---|
| `NETFORGE_TASK_ID` | The task's id |
| `NETFORGE_VARS_FILE` | Path to the validated variables, as JSON |
| `NETFORGE_OUTPUT_FILE` | Write a JSON object here to set the task result (optional) |

Stdout and stderr become the task log, and exit code 0 means success. The child
receives `PATH`, `HOME`, the locale, `NAUTOBOT_*`, `ANSIBLE_*`, `PYTHON*` and
`TF_*`, but never the worker's database or Redis credentials. To pass other
settings through, add them in `src/netforge/worker/engines/base.py`.

Ansible also receives every variable as an extra var, marked `!unsafe` so that
user input is never evaluated as a Jinja template.

## Adding an engine

Terraform is the expected next one, and takes four steps:

1. Add `src/netforge/worker/engines/terraform.py`. An engine is a class with a
   `name` and a `run(context)` that returns the result:

   ```python
   class TerraformEngine:
       name = "terraform"

       def run(self, context):
           run_process(context, ["terraform", "init", "-input=false"])
           run_process(context, ["terraform", "apply", "-input=false", "-auto-approve"])
           return read_output(context)
   ```

2. Register it in `ENGINES` in `src/netforge/worker/engines/__init__.py`.
3. Add a `worker-terraform` target to the `Dockerfile` that installs the binary.
4. Add a Compose service using that target with `WORKER_ENGINES: terraform`.

Each engine has its own queue, so that worker scales separately, and a backlog in
one engine doesn't hold up another.

Two things to decide before shipping Terraform: where state lives, since worker
containers are disposable and need a remote backend, and whether `apply` should
run without an approval step.

## How failures are handled

Postgres is the source of truth, and Redis only signals that work is waiting.

| Failure | What happens |
|---|---|
| Redis is down when a task is submitted | The task is saved and accepted, then queued once Redis returns |
| Redis loses its data | Workers requeue waiting tasks from Postgres |
| Two workers receive the same task | The claim is an atomic update, so only one runs it |
| A worker dies mid-task | After 60 seconds without a heartbeat, the task is marked failed |
| A task runs too long | It is killed at `timeout_seconds` and marked failed |

A task interrupted mid-run is **never retried automatically**. It may have changed
a device part way through, so a person checks the target and resubmits.

## Data

All state is in named Docker volumes, so deleting or recreating containers is
safe.

| Volume | Contents |
|---|---|
| `nautobot_db_data`, `nautobot_redis_data` | Nautobot's database and cache |
| `nautobot_media`, `nautobot_git`, `nautobot_jobs` | Nautobot's files |
| `tasks_db_data` | Task history and logs |
| `queue_data` | The Redis queue |

`docker compose down` keeps your data. **`docker compose down -v` deletes all of it.**

## Moving to Kubernetes

The stack was built to map across without code changes:

| Compose | Kubernetes |
|---|---|
| `api`, `worker` | Deployments; both are stateless |
| `migrate`, `seed` | Jobs |
| `nautobot-volumes` | Not needed; use `securityContext.fsGroup` |
| Named volumes | PersistentVolumeClaims, or managed Postgres and Redis |
| `.env` | Secrets |
| `./automations` bind mount | Not needed; the files are baked into the image |

Use `/livez` for liveness and `/healthz` for readiness. Set the worker's
`terminationGracePeriodSeconds` above your longest task, since a stopping worker
finishes its current task first. Add login to the GUI before exposing it beyond
localhost, because it currently has none.

## Tests

```bash
docker build --target test -t netforge-test:dev .
docker run --rm netforge-test:dev
```

## Layout

```
automations/
  ansible/             ansible.cfg, collections, Nautobot inventory
  tasks/<name>/        One folder per task type
src/netforge/
  api/                 REST API and GUI
  worker/              Queue consumer
  worker/engines/      Engine contract and implementations
  migrations/          Task database schema
  catalog.py           Loads and validates task.yml
  seed.py              Creates the 10.0.0.0/16 pool in Nautobot
scripts/               init-env.py, smoke-test.py
```
