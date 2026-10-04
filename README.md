# ArenaOps infrastructure

This repository manages PostgreSQL, Keycloak, Caddy, isolated Docker networks and initial realm provisioning. **No deployment was performed for this refactor. Deploy SIT first.**

| Environment | Location / domain | Realm | Compose project / network | GitHub Environment |
| --- | --- | --- | --- | --- |
| DEV | Developer machine / localhost | `arena-dev` | `arenaops-dev` | None |
| SIT | `/opt/arenaops/sit` / `sit.arenaops.in` | `arena-sit` | `arenaops-sit` | `sit-infrastructure` |
| PROD | `/opt/arenaops/prod` / `arenaops.in` | `arena` | `arenaops-prod` | `production-infrastructure` |

## Repository layout

```text
.github/workflows/infrastructure.yaml
.env.example
.gitignore
README.md
docker/
  Caddyfile
  docker-compose.edge.yaml
  docker-compose.infra.yaml
  docker-compose.dev.yaml
keycloak/
  realm/
    arena-realm.dev.template.json
    arena-realm.sit.template.json
    arena-realm.prod.template.json
  themes/arena-login/login/                 # Existing theme preserved
scripts/
  common.sh
  config.py
  write-runtime-env.py
  prepare-vps.sh
  remote-apply.sh
  deploy-from-actions.sh
  apply-infrastructure.sh
  apply-edge.sh
  bootstrap-keycloak.sh
  bootstrap-keycloak.py
  dev.sh
  validate.sh
  validate-caddy.sh
tests/test_infrastructure.py
```

The ignored `implementation_plan/implementation_plan.md` records local implementation and validation details; do not commit it.

## DEV

Requires Docker Engine, Compose supporting `up --wait`, Python 3 and jq. Choose local-only database and admin credentials and a BFF secret; no credentials are supplied in Git.

```bash
cp .env.example .env
chmod 600 .env
# Fill every blank in .env using an editor.
./scripts/dev.sh start
./scripts/dev.sh logs
./scripts/dev.sh stop
```

DEV exposes PostgreSQL at `127.0.0.1:5432` and Keycloak at `http://localhost:9091/auth`; Caddy is not started. Run UI locally at ports 4200/4201 and the BFF with realm `arena-dev` and the locally chosen secret. Local realms accept localhost and 127.0.0.1 callback URLs, never LAN wildcard redirects.

**Destructive DEV reset: deletes the DEV PostgreSQL and other project volumes.** It refuses non-DEV configuration.

```bash
./scripts/dev.sh reset DELETE_DEV_DATA
```

## Configuration and secrets

Only these input names are supported (legacy `KEYCLOAK_*` names have been removed):

| Input | Source / meaning |
| --- | --- |
| `ARENA_ENV` | `dev`, `sit` or `prod`; workflow maps `production` to `prod` |
| `ARENA_DB_NAME`, `ARENA_DB_USERNAME`, `ARENA_DB_PASSWORD` | Required database credentials |
| `KC_ADMIN_USERNAME`, `KC_ADMIN_PASSWORD` | Required Keycloak bootstrap admin credentials |
| `KC_BFF_CLIENT_SECRET` | Required confidential BFF client secret |
| `CADDY_BIND_IP` | Required SIT/PROD VPS IPv4 address; GitHub Environment variable |
| `ARENAOPS_INFRA_ENV_FILE` | Temporary runtime env path consumed by deployment scripts |

`config.py` derives `ARENAOPS_DOMAIN`, `KC_REALM`, `KC_BASE_URL`, `KC_PUBLIC_URL`, localhost ports, target directory, project name and network from one mapping. These cannot be overridden through the env file. Files must be mode 0600. Simple unquoted values, single-quoted values and JSON double-quoted values are supported; values must be single-line. The workflow writer escapes dollars for dotenv. It parses files as data, never sources them as shell code. Compose consumes the parsed exported variables with `--env-file /dev/null` to prevent reading an unrelated `.env` or interpolating secret characters twice.

Create **both** GitHub Environments with independent values for these secrets:

```text
VPS_HOST
VPS_USERNAME
VPS_SSH_KEY
VPS_SSH_HOST_KEY
ARENA_DB_NAME
ARENA_DB_USERNAME
ARENA_DB_PASSWORD
KC_ADMIN_USERNAME
KC_ADMIN_PASSWORD
KC_BFF_CLIENT_SECRET
```

`VPS_SSH_HOST_KEY` is a complete trusted `known_hosts` line matching `VPS_HOST`, verified using your VPS provider console or another trusted channel. SSH host checking is mandatory. Set `CADDY_BIND_IP` as an Environment variable, not a secret. Use distinct DB names, users, passwords and admin/BFF secrets for SIT and PROD. GitHub cannot check equality across protected environments, so administrators must ensure independence.

Configure required reviewers and deployment branch restrictions for `production-infrastructure`; configure SIT protection as appropriate. Workflow code selects environments but cannot create GitHub approval rules. Grant the deployment account Docker access (equivalent to root) and the necessary reviewed noninteractive sudo permission for directory/network preparation.

Deployment writes SSH key, known-hosts and runtime env files under runner `/dev/shm` with `umask 077`. Only repository configuration is copied to the VPS. Runtime secrets stream over verified SSH stdin into a remote `/dev/shm` mode-0600 file. EXIT/INT/TERM cleanup removes runtime directories on normal success and failure. No permanent `infra.env` or `app.env` is required. Docker retains container environment values in its privileged metadata, and Keycloak stores its confidential client secret in PostgreSQL; protect Docker access, database volumes and backups. Removing the transport file does not erase required running state. SIGKILL/host crashes cannot run shell traps; tmpfs disappears on reboot.

## SIT deployment: exact first deployment steps

1. Review and merge this change. Install Docker Engine, Compose supporting `up --wait`, Python 3, curl, jq and tar on the SIT VPS. Ensure the deployment account can access Docker and prepare `/opt/arenaops` through reviewed noninteractive sudo.
2. Point `sit.arenaops.in` DNS at the SIT VPS bind IP. Permit inbound TCP 80/443 and restrict SSH to operators. PostgreSQL and Keycloak host ports must remain private. Publish no IPv6 DNS record unless IPv6 exposure is configured separately.
3. Configure `sit-infrastructure` with the ten secret names above and its `CADDY_BIND_IP` variable. Ensure credentials differ from PROD.
4. In GitHub Actions → **ArenaOps Infrastructure** → **Run workflow**, select the reviewed branch, environment **sit**, operation **validate**, and run. This validates all three configurations without SSH or deployment.
5. Review backups/migration needs and the validation result. Run the workflow again with environment **sit**, operation **apply**, confirmation **APPLY**. Complete any Environment approval.
6. The workflow prepares `/opt/arenaops/sit`, `/opt/arenaops/edge` and both networks `arenaops-sit` / `arenaops-prod`, transfers repository files, starts and waits for PostgreSQL/Keycloak, bootstraps `arena-sit`, applies the shared Caddy project and marks `/opt/arenaops/sit/state/sit-infrastructure-applied` after health checks pass.
7. Inspect the public realm discovery URL `https://sit.arenaops.in/auth/realms/arena-sit/.well-known/openid-configuration`. Requests under `/auth/admin` and `/auth/realms/master` must return 404. The application routes return 502 until the SIT application stack is attached.

For approved operator-driven application of an already copied checkout, the equivalent remote command is:

```bash
sudo bash /opt/arenaops/sit/scripts/prepare-vps.sh sit
ARENAOPS_INFRA_ENV_FILE=/dev/shm/operator-runtime.env \
  bash /opt/arenaops/sit/scripts/apply-infrastructure.sh
# Operator is responsible for mode 0600 and cleanup of this manually created file.
```

The application repository uses projects `arenaops-sit-app` and `arenaops-prod-app`, environment-specific paths and credentials, and the corresponding single external network. Its explicit aliases are `<env>-arena-ui`, `<env>-arena-login`, and `<env>-arena-core`; internal Keycloak/database calls use `<env>-keycloak` and `<env>-postgres`. Publish no application ports. Keycloak and application database/schema provisioning remains an operator prerequisite.

## PROD preparation (do not deploy yet)

Prepare its own VPS/bind IP and DNS `arenaops.in`, configure `production-infrastructure` independently, and require Environment approval. Later follow the SIT procedure with workflow environment **production**, first **validate**, then a separately approved **apply / APPLY**. This maps to `/opt/arenaops/prod`, `arenaops-prod`, realm `arena`, localhost Keycloak port 29091, and `/opt/arenaops/prod/state/prod-infrastructure-applied`. Normal application pushes/releases cannot trigger infrastructure deployment.

## Networks, persistence and Caddy

`prepare-vps.sh sit|prod` creates the selected environment directories plus `/opt/arenaops/edge/docker` and both external networks. It stores no credentials. DEV remains separate on `arenaops-dev`. Only Caddy joins both SIT and PROD networks; environment services each join exactly one.

```text
Internet -> arenaops-edge-caddy :80/:443 (project arenaops-edge)
  sit.arenaops.in -> arenaops-sit -> sit-arena-ui / sit-arena-login / sit-keycloak
  arenaops.in     -> arenaops-prod -> prod-arena-ui / prod-arena-login / prod-keycloak
  private DBs: sit-postgres on arenaops-sit; prod-postgres on arenaops-prod
```

| Host | UI (remaining paths) | `/api` and `/api/*` | Allowed realm under `/auth/realms/` |
| --- | --- | --- | --- |
| `sit.arenaops.in` | `sit-arena-ui:80` | `sit-arena-login:7700` | `arena-sit` -> `sit-keycloak:8080` |
| `arenaops.in` | `prod-arena-ui:80` | `prod-arena-login:7700` | `arena` -> `prod-keycloak:8080` |

`/auth/resources/*` goes to the hostname's Keycloak. All remaining `/auth` paths return 404, including admin, master and the opposite environment's realm. Root `/health`, `/metrics`, `/admin`, `/management` and descendants also return 404. Keycloak paths are preserved. The API handler strips only the `/api` prefix: `/api/test?probe=1` reaches the BFF as `/test?probe=1`; `/api` and `/api/` reach `/`. HTTPS certificates and HTTP redirects for both hosts are automatic; HSTS, content-type/referrer headers and Caddy's standard forwarded headers remain enabled.

`docker/docker-compose.edge.yaml` owns the only Caddy listener, container `arenaops-edge-caddy`, and persistent volumes `arenaops-edge-caddy-data` / `arenaops-edge-caddy-config`. Set the **same** `CADDY_BIND_IP` in both GitHub infrastructure environments to the VPS bind address (or `0.0.0.0`). Application and infrastructure projects are `arenaops-<env>-app` and `arenaops-<env>`; DB volumes remain `arenaops-<env>_postgres_data`. Environment containers and explicit DNS aliases use `sit-` or `prod-` prefixes. Compose logical service keys retain automatic local aliases, but **no proxy or application upstream uses those ambiguous aliases**. Both explicit host routes and unique aliases prevent cross-environment selection; this is routing isolation, not isolation from a compromised shared edge.

PostgreSQL has no remote published ports. Keycloak publishes only loopback administration ports `127.0.0.1:19091` / `127.0.0.1:29091`; port 9000 and Caddy admin port 2019 stay unpublished. The UI refuses direct API/auth requests; the shared edge owns their routing. DB credentials and client secrets continue to come from GitHub environment secrets through temporary runtime files, never the shared Caddy configuration.

Either infrastructure apply validates its environment and updates the same canonical edge files under `/opt/arenaops/edge/docker`. The workflow serializes both environments with one concurrency group; `apply-edge.sh` also uses a VPS-wide `flock`, waits for Caddy health, then reloads the file explicitly. Both network names exist before the second environment is deployed; its host returns 502 until its services exist. Environment rollback does not roll back the shared edge: review shared configuration changes for both hosts.

### First shared-edge migration (operator action; not performed)

Back up both database volumes and existing Caddy certificate/config volumes. Stop and retire the old per-environment Caddy containers so they release 80/443; do not stop or remove PostgreSQL/Keycloak volumes. Review migration of old Caddy data into the new shared volume or allow fresh automatic issuance (consider certificate rate limits). Apply this infrastructure revision and the matching application revision for both environments to establish the new aliases. No script automatically removes old proxy containers or migrates persistent data.

Point both DNS names at this VPS, permit inbound TCP 80/443, configure the shared bind address identically, and retain protected GitHub environments. Existing container renames may require recreation; plan a maintenance window. Validate real HTTPS, discovery, login/callbacks and application health after deployment. Caddy health validates its admin API, not DNS, certificate issuance or upstream readiness. PostgreSQL password changes require separate rotation for existing volumes; never use remote `down --volumes`.

## Keycloak bootstrap and administration

All templates preserve OWNER/STAFF/ADMIN roles, public `arena-ui`, confidential service-account `arena-bff`, login theme and existing authentication defaults. UI uses PKCE S256. DEV uses local callbacks and `sslRequired=none`; SIT/PROD accept only their HTTPS origin and use `sslRequired=external`. No client secret or masked placeholder is stored in JSON. No exported scopes or token lifetimes existed in the repository, so Keycloak defaults remain; review these before PROD. Registration and password reset remain enabled; SMTP is still unconfigured.

`bootstrap-keycloak.sh TEMPLATE` requires `KC_REALM`, `KC_BASE_URL`, `KC_ADMIN_USERNAME`, `KC_ADMIN_PASSWORD`, `KC_BFF_CLIENT_SECRET`. It waits for internal readiness, authenticates to master, renders a mode-0600 temporary JSON, creates the target realm only if missing, and grants missing `manage-users`, `view-users`, `view-realm` roles. It removes temporary files on errors and never logs tokens/credentials or places them in command arguments. Reruns **do not update existing realm settings or rotate its BFF secret**; use an explicit reviewed migration/rotation. Bootstrap credentials likewise do not reset an existing admin password.

Public access is restricted by a realm allowlist in Caddy, independently of `KC_HOSTNAME`. Administrators can use `kcadm.sh` inside the selected Keycloak container on its private network, or the internal REST API through SSH:

```bash
# Run on the operator's machine; replace VPS_HOST/VPS_USERNAME locally.
ssh -N -L 19091:127.0.0.1:19091 VPS_USERNAME@VPS_HOST
# In a second terminal, internal API readiness (SIT):
curl -f http://127.0.0.1:19091/auth/realms/master/.well-known/openid-configuration
```

PROD uses port 29091. Supply admin credentials interactively or from a protected tool credential store when using administration tools, never command-line literals. These tunnels support REST/CLI administration. Although the admin hostname is loopback, **browser Admin Console login can redirect to the public master frontend hostname, which Caddy deliberately blocks**. Use CLI/API administration; browser use requires a separately reviewed private TLS/hostname access arrangement. Do not open master publicly to work around it. Replace temporary bootstrap admin accounts with permanent, least-privilege administrative accounts through Keycloak's documented procedure before PROD.

## Validation and rollback

```bash
./scripts/validate.sh
./scripts/validate-caddy.sh
# Equivalent syntax/JSON checks:
for script in scripts/*.sh; do bash -n "$script"; done
jq empty keycloak/realm/*.json
```

The test suite executes `docker compose ... config --format json` with dummy values for DEV, SIT and PROD and checks isolation, private ports, required variables, realms, routing configuration, workflow gating, secret serialization and bootstrap idempotency against a mock HTTP server. CI also runs Caddy validation and live route-protection containers with no network or exposed ports for SIT/PROD.

Rollback code/config to a reviewed prior version and reapply **the same environment** with temporary secrets. Take environment-specific PostgreSQL backups first; a code rollback does not undo realm/database mutations. Do not attach the old shared volume to either new environment without a reviewed migration and backup. Existing `/opt/arenaops/infra`, shared `arenaops` network, old state markers and persistent env files are not automatically migrated or removed; review and retire them separately after securing backups. Existing services may occupy ports 80/443 and must be handled before a new apply.

Implementation references: [Keycloak container health checks](https://www.keycloak.org/observability/health), [Keycloak management interface](https://www.keycloak.org/server/management-interface), [Caddy matchers](https://caddyserver.com/docs/caddyfile/matchers), and [Caddy reverse proxy forwarding](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
