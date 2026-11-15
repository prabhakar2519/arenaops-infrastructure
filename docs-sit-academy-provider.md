# SIT academy staff setup provider

The optional `docker-compose.sit-academy.yaml` mounts the already-tested academy provider only when `keycloak/providers/academy-keycloak-provider.jar` is installed. DEV and PROD are unchanged. No provider JAR or mail credentials are committed.

Build the JAR from the matching application release (`keycloak/academy-provider/pom.xml`). Install it at `/opt/arenaops/sit/keycloak/providers/academy-keycloak-provider.jar` (0644) and install `keycloak/themes/arena-academy` from that release alongside the existing login theme (directories 0755, files 0644). Do not replace the login theme directory. Apply only the SIT Keycloak service through `scripts/common.sh` after loading the existing SIT environment; do not restart PostgreSQL or alter its volume.

The provider registers `ARENA_STAFF_SETUP` for `arena-sit` as enabled/non-default and installs administrator-only academy attributes. Configure realm SMTP securely using the application's explicit `deploy/configure-academy-keycloak.py` and the existing operator/service-account credentials. The script also preserves the `basic` subject scope and adds the exact UI `/login` staff setup return address without widening redirects. Do not print or commit mail/admin secrets.

Before allowing Resend, verify readiness, required-action registration, email-theme availability and SMTP STARTTLS/authentication. Test provider account setup, one-time link replay and expiry using disposable Keycloak with captured SMTP, not a real customer mailbox. Do not remove this provider while outstanding staff setup links depend on it. Application image deployments alone do not install Keycloak providers or update existing realm SMTP.

This override was applied to SIT with Keycloak 26.5.3, preserving Core/BFF/UI/PostgreSQL containers. Merge this change before another infrastructure apply to preserve the opt-in mount. Keep the provider JAR/theme installed across future applies. If email delivery needs disabling, restrict invitation operations while investigating; do not bypass the one-time action or delete memberships. Revalidate the SPI before changing Keycloak versions.

Tests: `python3 -m unittest discover -s tests -p test_sit_academy_provider.py -v` (4 passed).
