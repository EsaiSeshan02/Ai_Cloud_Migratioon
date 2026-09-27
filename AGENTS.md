# AGENTS.md — AI Cloud Migration Assistant

## 1. Project identity

This repository is the user's **AI-Based Cloud Migration Assistant**.

Primary prototype workflow:

**AWS → Azure**

The application is a Flask/Python web application that scans cloud resources, analyzes them, maps source services to target services, plans migrations, performs supported data migration, verifies results, and generates reports.

IMPORTANT:
- This project is separate from the user's **ScamShield AI** project.
- Do NOT add a chatbot, browser extension, SMS/email/URL scam detection, or ScamShield features.
- Do NOT replace the project with a new framework unless explicitly requested.
- Extend and repair the existing application.

## 2. Current repository observations

The current repository already contains:
- Flask application factory and routes
- Authentication routes/models
- AWS, Azure and GCP service modules
- AWS/Azure/GCP scanners
- AI analysis modules
- Cloud mapping modules
- S3 → Azure migration service
- Migration/report/project/user models
- Security module placeholders
- Extensive existing frontend templates/CSS/JS/assets
- Pixel-oriented fonts/assets and migration illustrations

The repository also contains a local Python virtual environment under `myaicloudmig/`.
Treat it as an environment artifact, not application source code.

The archive may also contain generated `__pycache__` files and a SQLite database. Do not treat generated artifacts as source code.

## 3. Non-negotiable product requirements

The finished prototype must support the following conceptual workflow:

1. User authentication
2. Connect source cloud
3. Connect target cloud
4. Scan source resources
5. Identify cloud-specific services
6. Map AWS services to Azure equivalents
7. Perform compatibility analysis
8. Generate migration recommendations/plan
9. Execute supported migrations
10. Use chunked/batch data transfer for large data
11. Track progress
12. Resume interrupted migration safely
13. Verify migrated data/resources
14. Test/validate migrated application/resources where feasible
15. Generate a migration report
16. Protect credentials and sensitive data

### AWS → Azure mappings

At minimum, support the existing prototype mappings where technically appropriate:
- EC2 → Azure Virtual Machines
- S3 → Azure Blob Storage
- RDS → an appropriate Azure database target

Lambda and additional services should be architected so mappings can be added cleanly. Do not claim that every AWS service is automatically migrated.

## 4. Migration engine requirements

The migration engine must:
- Stream large objects instead of loading entire files into RAM.
- Support logical batches, with the current target concept of approximately 10 GB per batch.
- Track object/resource status.
- Record progress persistently where practical.
- Handle failures without falsely reporting success.
- Support safe resume/retry after interruption.
- Verify transferred objects using size/checksum/other appropriate validation.
- Avoid duplicate or corrupt transfers during retry.
- Expose useful progress information to the UI.
- Clearly distinguish completed, failed, skipped, pending and manual-review resources.

Do not implement fake migration progress or simulated success when real cloud APIs are available.

## 5. AI requirements

The existing AI layer should remain an orchestration/analysis component.

Use deterministic mapping rules for known service mappings and AI for:
- compatibility reasoning
- migration recommendations
- configuration analysis
- manual-review explanations
- source-code/dependency analysis where applicable

Never allow an AI response alone to execute arbitrary cloud operations.

Validate AI-generated structured output before using it.

If an API key is missing, the application should degrade gracefully with deterministic rules rather than crashing.

## 6. Security requirements

Security is a first-class requirement.

Implement/review:
- password hashing using a modern password hashing mechanism
- secure session/authentication handling
- authorization checks
- encryption for sensitive credentials/data stored by the application
- safe environment-variable based secrets
- no secrets hardcoded in source
- no cloud credentials printed to logs
- no credentials returned to browser JavaScript
- secure error messages
- input validation
- CSRF protection where applicable
- safe file upload handling
- audit logging for sensitive migration actions

Never commit real credentials.

Never print the contents of `.env`.

If a secret is discovered in source/history, flag it and recommend rotation rather than reproducing it.

## 7. Existing architecture

Prefer the existing structure:

app/
  ai/
  database/
  mappers/
  models/
  routes/
  scanners/
  security/
  services/
  static/
  templates/
  utils/

Keep business logic in services rather than placing large amounts of logic in Flask route functions.

Keep cloud-specific SDK logic in service/scanner modules.

Keep mapping definitions centralized and extensible.

## 8. Frontend requirements

Preserve the existing design language instead of replacing it.

The UI should retain:
- premium pixel-fusion aesthetic
- pixel-inspired typography
- Press Start 2P / Pixelify Sans where appropriate
- Manrope/modern body typography where already used
- gold brand accent around #D4AF37
- warm/champagne/graphite/cloud-white visual system
- light/dark support where already implemented
- responsive layouts
- AWS → Azure visual migration concept
- terminal-style UI
- floating cards/tiles
- cloud illustrations
- migration dashboards
- GSAP/animation work where appropriate

Do not remove existing assets or rewrite all CSS simply for stylistic preference.

Avoid excessive animation that harms accessibility or performance.

## 9. UX requirements

The main user journey should be understandable:

Connect Clouds
→ Scan
→ Analyze
→ Review Mapping
→ Configure Migration
→ Start Migration
→ Monitor Progress
→ Verify
→ Report

Errors must be visible and understandable.

The UI must never display a successful migration state unless the backend actually reports success.

## 10. Prototype vs production boundary

This is a college/project prototype, but its architecture should be production-aware.

It is acceptable to support a limited set of resources initially.

When a service cannot be automatically migrated:
- identify it
- show its mapped target if known
- explain limitations
- mark it as manual review
- do not pretend it migrated

Do not over-engineer Kubernetes, Terraform, Jenkins, multi-region orchestration, or every possible AWS/Azure service unless explicitly requested.

## 11. Database requirements

Use the existing SQLAlchemy models and migrations where possible.

Persist important migration state instead of relying entirely on Python dictionaries/in-memory state.

Migration records should be sufficient to resume or audit an operation.

Do not silently destroy the existing database.

Before destructive schema changes:
- inspect existing models/migrations
- create a migration
- preserve existing user/project/report data

## 12. Testing requirements

Before declaring a feature complete:
- run syntax/import checks
- run available tests
- add focused tests for new backend behavior
- test failure paths
- test authentication/authorization
- test migration retry/resume logic
- test mapping behavior
- test report generation
- test that missing credentials/API keys fail safely

Do not test against real production cloud resources unless explicitly authorized.

Prefer mocked cloud clients and small local fixtures for automated tests.

## 13. Working method for Codex

Work incrementally.

FIRST:
- inspect the repository
- inspect relevant files
- inspect routes/models/services
- identify current behavior
- run safe checks
- produce a concise audit

DO NOT immediately rewrite the application.

For each task:
1. State what you found.
2. Make the smallest coherent change.
3. Run relevant tests/checks.
4. Review the diff.
5. Fix regressions.
6. Report changed files and verification.

Do not modify unrelated files.

Do not regenerate the entire frontend or backend when a targeted change is sufficient.

## 14. Important repository hygiene

Ignore these as source:
- `myaicloudmig/`
- `__pycache__/`
- `*.pyc`
- generated reports/uploads unless intentionally tracked
- local database artifacts when appropriate

The repository currently appears to lack a normal `.gitignore` file. Create one if necessary, but do not delete user files.

At minimum, consider:
.env
__pycache__/
*.pyc
myaicloudmig/
instance/
*.db
app/uploads/
reports/

Do not automatically delete existing files. Explain proposed cleanup first when it could remove user data.

## 15. Completion criteria

Do not say the project is complete merely because the Flask server starts.

The core demonstration should be able to show:

AWS credentials
→ AWS connection verification
→ resource discovery
→ service mapping
→ compatibility/recommendation
→ migration plan
→ supported S3 → Azure Blob migration
→ batch/progress handling
→ retry/resume behavior
→ verification
→ migration report

with secure handling and clear UI states.

## 16. Priority order

When resolving conflicts, prioritize:

1. Security
2. Correctness
3. Existing working functionality
4. Data integrity
5. Migration reliability/resume behavior
6. Testability
7. Maintainability
8. UI polish
9. Animation

## 17. Do not do these things

- Do not expose secrets.
- Do not invent successful cloud operations.
- Do not silently delete the database.
- Do not replace Flask with another framework.
- Do not mix ScamShield AI features into this project.
- Do not add a chatbot.
- Do not add a browser extension.
- Do not claim full automatic migration of unsupported services.
- Do not hardcode cloud credentials.
- Do not make large unrelated refactors.
