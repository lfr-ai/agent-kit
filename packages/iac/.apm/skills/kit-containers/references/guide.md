# Container review guide: gates, failure modes, and recovery

## Reference map

| Concern | Reference |
| --- | --- |
| Multi-stage builds, caching, build secrets, context, reproducibility | [Build patterns](build-patterns.md) |
| Non-root users, minimal bases, health, signals, runtime limits | [Runtime hardening](runtime-hardening.md) |
| Hadolint, SBOM, scanning, provenance, registry hygiene | [Supply chain](supply-chain.md) |

## Quality gates

- Base images are pinned by digest from trusted registries.
- The final stage holds only runtime artifacts and ends with a numeric
  non-root `USER`; application files are root-owned.
- No credentials in `ARG`, `ENV`, copied files, or image history; build
  secrets use secret mounts; `.dockerignore` excludes secret files.
- Exec-form entrypoint with `SIGTERM` handling or an init process.
- Liveness and readiness are defined in the image or the orchestrator.
- Hadolint passes; shipped images have provenance and pass a built-image
  vulnerability gate. SBOM generation follows the release inventory requirement.
- Runtime configuration uses a read-only root filesystem, dropped
  capabilities, `no-new-privileges`, and resource limits.

## Failure modes

- A credential passed as a build argument is visible in `docker history`.
- `COPY . .` without `.dockerignore` ships `.env`, `.git`, or state files.
- Shell-form entrypoint swallows `SIGTERM`; the container is killed after the
  grace period and in-flight work is lost.
- An unpinned tag silently pulls a new base with different libraries.
- Health checks call `curl`, which is missing from slim images, so the
  container is always unhealthy.

## Negative cases

- `FROM node:latest`, `FROM python:3` without a digest.
- No `USER` instruction, or `USER root` in the final stage.
- `ARG NPM_TOKEN` or `ENV API_KEY=...`.
- `ENTRYPOINT npm start` (shell form).
- `ADD https://...` for remote files without checksum verification.

## Recovery

1. Rotate any secret that reached a layer, then rebuild without it; deleting
   it in a later layer does not remove it.
2. Pin bases by digest and enable automated digest updates.
3. Move build-only tools to an earlier stage and copy only artifacts.
4. Switch to exec form and add signal handling or `init`.
5. Rebuild, scan again, and deploy by digest.

## Prerequisites

- The Dockerfile, `.dockerignore`, build command, and a listing of the build
  context.
- The orchestrator manifest or compose file that runs the image.
- The organization's registry, base image, and scan policies.

## Templates

- [Python Dockerfile](../assets/templates/Dockerfile.python.template)
- [Node.js Dockerfile](../assets/templates/Dockerfile.node.template)
- [.dockerignore](../assets/templates/dockerignore.template)
- [Compose](../assets/templates/compose.yaml.template)
- [Hadolint configuration](../assets/templates/hadolint.yaml.template)

Every `PIN_IMAGE_DIGEST` placeholder must be replaced with a reviewed digest;
until then the build fails by design.

## Sources

- <https://docs.docker.com/build/building/best-practices/>
- <https://docs.docker.com/engine/security/>
