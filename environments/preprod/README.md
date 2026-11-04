# PRE-PROD Environment

This folder contains PRE-PROD-only configuration templates and validation
steps. Do not copy DEV credentials, endpoint values, or database contents into
PRE-PROD.

## Local Configuration

1. Use the same Python runtime and dependencies as the application. From the
   repository root, create a virtual environment and install `requirements.txt`.
2. Copy `preprod.env.example` to `preprod.env` and supply PRE-PROD metastore
   settings and secrets through the organization's approved secret store.
3. Copy `setup.example.json` to `setup.json` and replace every placeholder with
   the approved PRE-PROD tenant, project, environment, source, and target
   metadata. Keep passwords out of this JSON file.
4. Ensure the shared metastore has the required `sec` and `conn` schema and
  identity columns. Use a dedicated PRE-PROD metastore service account, and
  configure distinct PRE-PROD source and target databases, accounts, and
  secret values.

The DEV example identifies the shared metastore endpoint as
`192.168.11.91:5432/Futran`; the PRE-PROD example reuses only that endpoint.
It does not reuse the DEV username or password. The DEV configuration notes
that this server does not support SSL, so the template currently sets
`MDIP_METASTORE_SSLMODE=disable` for connectivity. Enable TLS and switch to
`verify-full` before PRE-PROD sign-off, or obtain a documented security
exception from the infrastructure owner.

`preprod.env` and `setup.json` are ignored by Git. The app selects the explicit
environment file through `MDIP_ENV_FILE`; when it is set, that file is
authoritative. With no `MDIP_ENV_FILE`, existing DEV behavior continues to
load `.env` through python-dotenv. In hosted PRE-PROD, prefer environment
variables injected by the approved secret/configuration manager and do not
deploy a developer's `.env` file.

## Initial Registration and Validation

Run the `setup` command once, after the PRE-PROD databases and metadata schema
are provisioned. It validates endpoints and writes connection metadata:

```powershell
$env:MDIP_ENV_FILE = (Resolve-Path .\environments\preprod\preprod.env).Path
.\.venv\Scripts\python.exe -m incremental_loading.scripts.dynamic_source_target_setup setup --config .\environments\preprod\setup.json --non-interactive
```

After registration, validate the metastore schema, saved connection profiles,
network connectivity, credentials, and required database grants:

```powershell
.\environments\preprod\validate.ps1
```

The validator uses `inspect-schema` and `validate`; it does not create or alter
metadata. It reports failure if the local Python environment, PRE-PROD files,
metastore schema, saved profiles, endpoint connectivity, or privileges are not
ready. Do not run `setup` repeatedly against a shared environment without
reviewing its idempotency and intended changes.

## Infrastructure and Access Readiness

- Use the approved shared metastore with a dedicated PRE-PROD service account
  and separate PRE-PROD environment records. Provision isolated PRE-PROD
  source/target endpoints using approved, non-production test data. Match
  DEV's required PostgreSQL schema and connector versions while keeping
  source/target hosts, databases, accounts, and secrets distinct.
- Permit network access only from approved PRE-PROD application hosts or VPN
  ranges to the required PostgreSQL endpoints. Confirm DNS, routing, firewall
  rules, and TLS certificates; `verify-full` is the template default.
- Give the application identity only the database and schema privileges
  needed by its role. The initial `setup` identity must also be authorized to
  register the required metadata records.
- Grant environment access to the authorized team group through the
  organization's identity provider, host/VPN policy, database roles, and
  secret-store ACLs. This repository cannot provision those external
  permissions by itself.
- Promote changes from DEV through reviewed commits or pull requests and the
  team's deployment process. Do not promote `.env` files, credentials, virtual
  environments, or DEV database data.

## Required Values Before Sign-Off

The environment is not considered provisioned until the infrastructure owner
provides PRE-PROD source/target hostnames and database names, TLS requirements
and CA chain, network allow-list, PRE-PROD service-account name and credential,
secret-store references, authorized team group, and deployment runner/host.
The shared metastore TLS gap must also be resolved or formally accepted. Run
connectivity checks from the deployment runner or host, not only from a
developer workstation.
