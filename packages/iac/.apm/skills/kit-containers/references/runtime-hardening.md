# Runtime hardening: users, bases, health, signals

## Non-root users

- End every image with `USER <uid>:<gid>` using a fixed numeric non-zero ID
  (for example 10001). Numeric IDs let Kubernetes `runAsNonRoot` verify the
  user without reading `/etc/passwd`.
- Keep application files owned by root and read-only to the runtime user;
  give the process write access only to explicit volumes or `tmpfs` paths.
- Do not install `sudo`; do not rely on `setuid` binaries.

## Minimal bases

| Base family | Shell and package manager | Use when |
| --- | --- | --- |
| `*-slim` (Debian) | Yes | Default; broad compatibility with glibc wheels |
| `alpine` | Yes (musl libc) | Small images; verify native packages work with musl |
| Distroless | No | Hardened runtime; debug with ephemeral debug containers |
| `scratch` | No | Static binaries only |

Fewer packages mean fewer CVEs and less for an attacker to use. Choose the
smallest base that runs the application without workarounds, and rebuild on
base image updates.

## Health checks and probes

- Expose a cheap `/healthz` (liveness: process can serve) and, where needed,
  `/readyz` (readiness: dependencies reachable).
- `HEALTHCHECK` is used by Docker and Compose. Kubernetes ignores it and uses
  pod probes; when the orchestrator owns probing, document the probe instead
  of adding an image health check.
- Implement the check with tools already in the image (the interpreter);
  installing `curl` only for health checks enlarges the attack surface.
- Set `--start-period` so slow starts are not killed.

## Signals and shutdown

- Use exec-form `ENTRYPOINT ["binary", "arg"]`. Shell form wraps the process
  in `/bin/sh -c`, which does not forward `SIGTERM`.
- The kernel gives PID 1 no default signal handlers. Handle `SIGTERM` in the
  application (stop accepting work, drain, exit) or run an init process
  (`docker run --init`, Compose `init: true`).
- Align the shutdown budget: orchestrator grace period (Compose
  `stop_grace_period`, Kubernetes `terminationGracePeriodSeconds`) must exceed
  the application's drain time.

## Runtime restrictions

- Run with a read-only root filesystem and mount `tmpfs` for scratch space.
- Drop all Linux capabilities and add back only what is required; set
  `no-new-privileges`.
- Set CPU and memory limits; size memory so the runtime (JVM heap, Node
  `--max-old-space-size`) fits below the container limit.
- Inject configuration through environment variables and secrets through the
  platform secret mechanism (files under `/run/secrets`, mounted secret
  volumes, or workload identity). Never bake them into layers.

## Review checklist

- [ ] Final `USER` is a numeric non-root ID; files are root-owned read-only.
- [ ] Base image is the smallest that works, pinned by digest.
- [ ] Liveness and readiness are defined in the image or the orchestrator.
- [ ] Exec-form entrypoint; `SIGTERM` handled or an init process used.
- [ ] Read-only root filesystem, dropped capabilities, resource limits.

Templates: [Compose](../assets/templates/compose.yaml.template),
[Python Dockerfile](../assets/templates/Dockerfile.python.template),
[Node.js Dockerfile](../assets/templates/Dockerfile.node.template).

## Sources

- <https://docs.docker.com/build/building/best-practices/#user>
- <https://docs.docker.com/reference/dockerfile/#healthcheck>
- <https://docs.docker.com/reference/dockerfile/#entrypoint>
- <https://docs.docker.com/reference/cli/docker/container/run/#init>
- <https://docs.docker.com/engine/security/>
- <https://docs.docker.com/reference/compose-file/services/>
- <https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/>
- <https://kubernetes.io/docs/tasks/configure-pod-container/security-context/>
