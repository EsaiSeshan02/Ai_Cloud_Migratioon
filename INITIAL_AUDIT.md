# AI Cloud Migration — Initial Repository Audit

## Backup

The supplied ZIP should be retained as the original safety backup. Work on a separate copy/branch when using Codex.

## Repository snapshot

The archive contains the main Flask application plus a bundled local Python virtual environment.

Application areas found:
- `app/ai/`
- `app/database/`
- `app/mappers/`
- `app/models/`
- `app/routes/`
- `app/scanners/`
- `app/security/`
- `app/services/`
- `app/static/`
- `app/templates/`
- `app/utils/`

The archive also contains approximately 11,675 files under `myaicloudmig/Lib/site-packages`, which appears to be a bundled Python virtual environment. Codex should ignore that directory.

## Existing functionality/components observed

### Cloud and migration
- AWS service/session handling
- Azure service/session handling
- GCP service module
- AWS/Azure/GCP scanners
- AWS/Azure/GCP mapping structures
- AI resource analysis
- migration planning
- S3 → Azure Blob migration service
- logical 10 GB migration batching
- streamed object transfer
- object-level migration tracking code

### Frontend
The project already has substantial frontend work:
- landing page
- dashboard
- migration pages
- AWS/Azure/GCP source pages
- connect-cloud page
- scan page
- configure migration page
- migration dashboard
- report page
- responsive CSS
- animation JS
- GSAP asset
- pixel fonts
- cloud logos
- migration illustrations
- terminal/dashboard imagery

### Database/models
Models found include:
- User
- Project
- Migration
- Report
- MigrationFile (referenced by migration service)

A SQLite database is bundled.

## Important findings requiring Codex attention

### 1. Security modules are currently empty

The following files were found with zero bytes:
- `app/security/credential_manager.py`
- `app/security/encryption.py`
- `app/security/audit_logger.py`

These should become an early security task.

### 2. Mapping file is partly hard-coded

`app/mappers/cloud_mapper.py` contains mappings for AWS/Azure/GCP. This should be made consistent and extensible rather than scattering mapping rules throughout the code.

### 3. In-memory migration sessions exist

AWS/Azure connection sessions are stored in Python dictionaries in service modules. This is acceptable for an early prototype, but it prevents reliable multi-process persistence and weakens resume behavior.

Important migration state should move toward persistent storage.

### 4. S3 migration already has meaningful implementation

The S3 migration service explicitly describes:
- 10 GB logical batch limit
- streaming instead of loading an entire bucket into RAM
- object-level tracking
- Azure storage account/container handling

Codex should inspect and extend this implementation rather than replacing it.

### 5. AI engine currently uses mapping rules

The existing AI engine calls the cloud mapping layer and generates recommendations. Preserve this architecture and add AI capabilities around deterministic mappings rather than allowing unconstrained AI output to directly perform cloud operations.

### 6. Configuration

`config.py` loads environment variables and contains:
- Flask secret key
- database URL
- credential encryption key
- upload configuration
- 10 GB batch-size configuration

The fallback Flask secret key should not be acceptable for production-like deployment.

### 7. `.env`

An `.env` file exists in the archive and is currently empty in the supplied ZIP. Keep it out of version control.

### 8. README

`README.md` is empty and should eventually document:
- setup
- environment variables
- architecture
- supported migrations
- limitations
- testing
- demo workflow

## Recommended implementation order

1. Repository cleanup/hygiene
2. Security layer
3. Persistent migration state
4. AWS/Azure connection and scanning hardening
5. Mapping engine
6. AI analysis
7. S3 → Azure batch/resume/verification
8. Reports
9. Application/resource validation
10. Automated tests
11. Frontend integration/polish
12. README and final demo documentation

## Prototype boundary

The project should demonstrate real migration for the supported path(s), especially S3 → Azure Blob, while clearly marking unsupported services for manual review.

It should not pretend to automatically migrate every AWS service.
