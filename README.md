# ArenaOps Infrastructure

This repository owns PostgreSQL, Keycloak, Caddy/TLS, the private Docker network, and initial realm provisioning. It contains no application source or real credentials.

Pull requests validate configuration. Production apply is manual through `workflow_dispatch`, requires operation `apply`, typed confirmation `APPLY`, and approval from the `production-infrastructure` GitHub Environment.

## First deployment

1. Install Docker Engine and Compose on the Hetzner VPS.
   The deployment user must be in the Docker group and have passwordless sudo permission for the reviewed `prepare-vps.sh` command.
2. Point production DNS to the VPS.
3. Create `/opt/arenaops/config/infra.env` and `app.env` with mode `0600`.
4. Configure `VPS_HOST`, `VPS_USERNAME`, and `VPS_SSH_KEY` as environment secrets.
5. Run infrastructure validation.
6. Review backups and configuration, then run apply with confirmation `APPLY`.

Realm templates contain `**********` instead of the confidential client secret. Bootstrap injects the secret into a temporary file and removes it after use.
