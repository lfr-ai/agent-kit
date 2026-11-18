# Repository ownership

This repository owns one toolkit, not consumers' project context.

| Project | Ownership | Facts |
| --- | --- | --- |
| Agent Kit | Canonical portable capabilities and validation | [PROJECT.md](PROJECT.md) |
| Delivery | Reusable native CI and policy sources | [Package guide](packages/delivery/README.md) |
| Runtime | Independently installable Python application foundation | [Package guide](packages/runtime/README.md) |
| Starter | Copier-generated consumer manifests with APM-owned capabilities | [Package guide](packages/starter/README.md) |

Consumer repositories keep their own PROJECT.md, llms.txt, knowledge, and memories.
No company workspace list or machine-specific path is published here.
The [platform sequence](docs/platform-implementation.md) distinguishes foundations
from application, cloud and publication work that remains unimplemented.
