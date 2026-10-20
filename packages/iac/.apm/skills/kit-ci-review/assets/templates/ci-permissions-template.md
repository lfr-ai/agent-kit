CI Permissions & Publishing Job Template

Description: Document which workflows/jobs may publish artifacts or access secrets, the protected environments required, and the minimum permissions.

- Workflow file: .github/workflows/ci.yml
- Publishing job: build-and-publish
- Required environment: production-publish (with reviewers: X, Y)
- Minimal permissions:
  - contents: read
  - id-token: write-only to environment
  - packages: write (only on protected branch)
- Approval process:
  - PR must be reviewed by owners listed in CODEOWNERS
  - Publishing job can be triggered only from protected branch merge or explicit environment approval
- Evidence required for publish:
  - checksum of artifact
  - changelog entry
  - release owner acknowledgment
