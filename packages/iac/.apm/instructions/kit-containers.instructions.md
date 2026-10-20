---
description: Apply to container build definitions and image-related configuration.
applyTo: "**/Dockerfile,**/Containerfile,**/docker-compose*.yml,**/compose*.yaml"
---

- Pin base images by explicit tag and digest from a trusted registry, and update them through the dependency workflow.
- Use multi-stage builds and keep compilers, package caches, and build-only tools out of runtime layers.
- Exclude secrets, VCS metadata, local caches, and unrelated source from the build context with an ignore file.
- Pass build-time secrets through BuildKit secret mounts, never `ARG`, `ENV`, or copied files.
- Order layers for cache reuse: copy dependency manifests and install before copying application source.
- Run as a non-root user with a fixed UID, a read-only root filesystem where feasible, and explicit writable paths.
- Use exec-form `ENTRYPOINT` and `CMD` so the process receives signals; handle `SIGTERM` and exit within the stop timeout.
- Define readiness and health behavior that reflects actual service availability, not only process liveness.
- Set resource limits and drop unneeded Linux capabilities in compose or orchestrator configuration.
- Log to standard output and error, not to files inside the container.
- Never bake credentials, environment-specific configuration, or private data into an image.
- Scan images and produce an SBOM in CI; fail on fixable critical vulnerabilities according to policy.
- Use the `kit-containers` skill for build and review procedures.
