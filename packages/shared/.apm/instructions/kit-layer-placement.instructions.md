---
description: Apply when adding or moving modules between domain, application, infrastructure, presentation, and composition layers.
applyTo: "**/domain/**,**/application/**,**/infrastructure/**,**/adapters/**,**/presentation/**,**/composition/**,**/ports/**"
---

- Place code by role: domain holds rules and value types; application holds use-case sequencing and ports; infrastructure holds adapters for files, processes, databases, and providers; presentation holds input parsing and output formatting; composition wires them.
- Dependencies point inward only: presentation and infrastructure may import application and domain, application imports domain, and domain imports neither.
- Define a port (protocol or interface) in the inner layer that needs it and implement it in an outer adapter.
- Keep framework, ORM, SDK, and transport types out of domain and application signatures.
- Name a module after its responsibility (`invoice_repository`, `export_command`), not a generic bucket such as `utils`, `helpers`, or `misc`.
- Reserve orchestrator or coordinator modules for code that sequences several use cases; a single use case belongs in its application service.
- Instantiate concrete adapters only in the composition root; inner layers receive collaborators by injection.
- Load configuration at the edge and pass typed values inward.
- Move a misplaced module together with its tests and import updates in one change; do not leave forwarding shims without a removal plan.
- Use the `kit-hexagonal-architecture` skill for boundary design and import-rule checks.
