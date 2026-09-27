# AI Cloud Migration Assistant

An AWS-to-Azure migration assessment prototype with real execution for **AWS S3
to Azure Blob Storage** and a deliberately narrow **Python ZIP AWS Lambda to an
existing Azure Function App** path. It preserves a deterministic safety boundary:
EC2, RDS, and DynamoDB are assessment/planning or manual-review paths, not
automatic migrations.

## Architecture

- `app/routes/`: authenticated Flask pages and JSON APIs.
- `app/scanners/`: normalized AWS EC2/S3/RDS/Lambda and Azure VM/Storage/SQL discovery.
- `app/mappers/cloud_mapper.py`: authoritative deterministic capability mappings.
- `app/services/migration_plan_service.py`: persisted owner-scoped preflight plans.
- `app/services/s3_migration_service.py`: real streaming S3-to-Blob work.
- `app/models/`: SQLAlchemy users, plans, migrations, object records, reports, and audit events.

## Supported capability

| Source | Target | Capability |
|---|---|---|
| S3 | Azure Blob Storage | Supported execution |
| EC2 | Azure Virtual Machine | Planning only |
| RDS PostgreSQL/MySQL/SQL Server | Engine-aware Azure database target | Planning only |
| Unknown RDS engine | Manual review | Manual review |
| Lambda | Azure Functions | Real execution for the documented narrow Python ZIP subset; all other cases require manual review |

## S3 execution behavior

Starting a migration uses AWS SDK object reads and Azure Blob SDK writes. Each
S3 response body is streamed directly to Azure; the application does not load a
complete object into memory. The approximately 10 GiB batches are **logical
scheduling batches**, not an application-managed multipart/block-upload
protocol. Azure SDK transport chunking remains SDK-controlled.

Migration and per-object state are persisted. Verified or destination-size
matched objects are skipped on resume; failed/incomplete objects are eligible
for bounded retry/resume. Verification is destination size/metadata validation.
S3 and Azure ETags are retained as provider metadata only and are **not** used
as a cross-provider cryptographic integrity assertion.

An execution can reference an approved persisted plan. A database-backed active
identity prevents duplicate active transfers for the same owner/source/
destination intent. A process restart marks queued/running work interrupted;
the user must reconnect both clouds and resume it. This is not a distributed
durable job queue.

If no selected destination storage account is supplied, the configuration UI
requires explicit acknowledgement that a new Azure Storage Account may be
provisioned. That action can create billable resources. Existing destination
objects are never overwritten: matching sizes are skipped and mismatches require
manual review.

## Lambda to Azure Functions behavior

The Lambda execution path is deliberately narrow. It supports only an existing
Azure Function App with explicit resource group and Function App name, a Python
3.10 or 3.11 AWS Lambda ZIP package, a `module.function` handler, no Lambda
layers, no VPC dependency, and no discovered AWS event-source mappings. The
application retrieves the real Lambda configuration and signed package location
through boto3, downloads and extracts the ZIP only in a temporary directory,
rejects unsafe archive paths, generates a minimal Azure Functions HTTP wrapper,
and submits the resulting ZIP to the existing Function App's Kudu ZIP-deploy
endpoint. It then re-reads the Function App through Azure management APIs.

Lambda deployment is synchronous in this prototype. If the application stops
while Kudu deployment or management-plane validation is in progress, the
persisted migration becomes `manual_review_required`; the application does not
guess the provider outcome and does not automatically resume it. Inspect the
existing Function App, then begin a fresh, approved deployment attempt only if
that inspection is safe.

Environment variable names are assessed, but their values are never copied to
Azure or persisted. AWS access-key environment variables are never transferred.
Container-image Lambdas, unsupported runtimes, layers, VPC functions, and AWS
event-source integrations are manual-review cases. The deployment route never
creates a Function App or reports success before Kudu returns success and the
management-plane validation succeeds.

## Local setup

```powershell
.\myaicloudmig\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:APP_ENV = "development"
python app.py
```

## Database schema migrations

Flask-Migrate/Alembic maintains the forward-only schema history in
`Migrations/`. Apply it explicitly before running a new persistent database or
upgrading a database created by an earlier release:

```powershell
$env:APP_ENV = "development"
flask --app app.py db upgrade
```

The baseline revision creates missing current tables and adds only required
legacy columns/indexes; it never drops tables or deletes migration data. The
application retains its additive startup compatibility check for older local
databases, but `flask --app app.py db upgrade` records the baseline revision
and is the reproducible deployment procedure. SQLite remains appropriate for
local development and a single-process demo, not multi-worker migration
execution. Existing historical duplicate object rows can prevent the legacy
unique object index from being created and must be reviewed manually before
retrying that upgrade.

For production-like configuration, set at least `SECRET_KEY`; startup rejects a
missing production secret. Common configuration includes `DATABASE_URL`,
`SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`, `HSTS_ENABLED`,
`HSTS_MAX_AGE`, and `CREDENTIAL_ENCRYPTION_KEY`. Do not commit `.env`.

## Cloud prerequisites

AWS credentials need STS identity verification plus discovery permissions for
the selected AWS services and S3 listing/object read access for a real transfer.
Azure service-principal access needs subscription/resource-group discovery,
Storage Account read/list-key permissions, Blob container/blob write access,
and—only when explicitly approved—Storage Account creation permissions.
Use dedicated least-privilege non-production accounts for demonstrations.

For Lambda migration, AWS also needs `lambda:GetFunction`,
`lambda:GetFunctionConfiguration`, and `lambda:ListEventSourceMappings` for the
selected function. Azure needs `Microsoft.Web/sites/read`, publishing-credential
read access, and ZIP deployment permission for the explicitly selected existing
Function App/slot. The Function App must already use a compatible Python Linux
runtime and have a deployment-capable configuration.

## Security model

Passwords use Bcrypt. Flask-Login, CSRF protection, HttpOnly/SameSite cookies,
owner-scoped plans/migrations/reports, safe error responses, redacted logging,
audit events, request limits, and configurable security headers are enabled.
Raw cloud credentials are transient in application memory and are not persisted
to SQLite, reports, plans, or browser responses. The credential-encryption
helper is available for a future explicitly approved encrypted-secret store;
the current application deliberately avoids such persistence.

## Tests

```powershell
.\myaicloudmig\Scripts\python.exe -m compileall -q app tests app.py config.py
.\myaicloudmig\Scripts\python.exe -m unittest discover -s tests -v
```

Automated tests mock provider APIs; they do not use real cloud credentials or
perform cloud migrations.

## Demonstration flow

Register → login → connect AWS → connect Azure → scan AWS → save/review plan
→ select an S3 resource → explicitly configure destination behavior → start
the real S3 transfer → monitor persisted progress → reconnect/resume if needed
→ open migration history/details → generate the persisted aggregate report.

The active configuration UI exposes execution controls only for S3 and the
separately gated Lambda workflow. EC2, RDS, and DynamoDB resources remain
assessment/manual-review items and do not show an executable migration control.

## Limitations

This is a production-oriented prototype, not a production deployment claim.
The in-process worker/execution-session design must be replaced with a shared
credential/session and durable job system for multi-process production use.
The included Alembic baseline provides safe, additive upgrades for existing
SQLite data. EC2/RDS/DynamoDB execution
must not be claimed until separate real execution, verification, cutover, and
rollback implementations exist. Lambda execution is limited strictly to the
documented Python ZIP subset and does not translate AWS triggers, IAM, VPC
configuration, AWS SDK usage, or secret environment variables.
