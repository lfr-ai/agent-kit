---
name: kit-containers
description: Use when reviewing container images, Dockerfiles, or runtime settings to ensure reproducible builds, isolation, and safe shutdown.
license: MIT
---

# Review container build and runtime

Container review covers what goes into the image, who the process runs as,
how it stops, and how the image is proven. It never pushes images or deploys.
Start with the [review guide](references/guide.md).

## Procedure

1. Identify the Dockerfile, `.dockerignore`, build command, target platform,
   and the manifest that runs the image (compose, Kubernetes, or platform
   configuration).
2. List the build context and confirm `.dockerignore` excludes VCS data,
   environment files, keys, local dependency folders, and infrastructure
   state ([build patterns](references/build-patterns.md)).
3. Check every `FROM`: trusted registry, explicit tag, and `@sha256:` digest.
   Note the base family and whether a smaller one would work
   ([runtime hardening](references/runtime-hardening.md)).
4. Check stage separation: dependency and build stages hold compilers and
   caches; the final stage copies only runtime artifacts; dependency
   manifests are copied and installed before source.
5. Search `ARG`, `ENV`, `COPY`, `ADD`, and `RUN` for credentials. Require
   secret mounts for private registries and SSH mounts for private Git.
6. Confirm the final `USER` is a fixed numeric non-root ID, application files
   are root-owned, and writable paths are explicit volumes or `tmpfs`.
7. Confirm exec-form `ENTRYPOINT`, `SIGTERM` handling or an init process, and
   a grace period longer than the drain time.
8. Confirm liveness and readiness: an image `HEALTHCHECK` using tools already
   present, or orchestrator probes when the platform owns probing.
9. Check runtime restrictions in the manifest: read-only root filesystem,
   dropped capabilities, `no-new-privileges`, CPU and memory limits, secrets
   from the platform mechanism.
10. Run or verify Hadolint, SBOM and provenance generation, and an image scan
    gate ([supply chain](references/supply-chain.md)). Record suppressions
    with reasons.
11. When proposing a new Dockerfile, adapt the
    [Python](assets/templates/Dockerfile.python.template) or
    [Node.js](assets/templates/Dockerfile.node.template) template, the
    [.dockerignore](assets/templates/dockerignore.template),
    [compose](assets/templates/compose.yaml.template), and
    [Hadolint](assets/templates/hadolint.yaml.template) templates, and build
    and test the real image before adoption.
12. Produce a remediation list ordered by severity: embedded secrets, root
    user, unpinned bases, missing signal handling, missing probes, missing
    limits, scan findings. Hand publishing to the release owner.

## Acceptance gates

- [ ] Every base image pinned by digest from a trusted registry.
- [ ] No secrets in build arguments, environment, layers, or context.
- [ ] Final stage runs as numeric non-root with root-owned app files.
- [ ] Exec-form entrypoint; graceful `SIGTERM` shutdown verified.
- [ ] Health or orchestrator probes defined and tested.
- [ ] Read-only filesystem, dropped capabilities, resource limits set.
- [ ] Hadolint clean; SBOM, provenance, and scan gate in CI.

## Out of scope

A review does not authorize a registry push or a deployment, and a template
is not evidence: build and run the consumer's actual image.
