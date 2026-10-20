# Build patterns: multi-stage, caching, secrets, reproducibility

## Multi-stage builds

- Separate stages for dependency resolution, compilation, and runtime. The
  final stage starts from a clean base and copies only the artifacts it runs
  (a virtual environment, compiled output, production `node_modules`).
- Compilers, package manager caches, test tools, and source files that are
  not executed stay in earlier stages and never reach the published image.
- Name stages (`AS build`, `AS runtime`) and copy with `COPY --from=<name>`.
  Use `--target` to build intermediate stages for tests in CI.
- Use the same base image (and digest) for build and runtime when copying
  interpreter-specific artifacts such as a Python virtual environment, so
  paths and ABI match.

## Layer order and caching

- Copy dependency manifests and lockfiles first, install, then copy source.
  A source edit then reuses the dependency layer.
- Use BuildKit cache mounts (`RUN --mount=type=cache,target=/root/.cache/pip`)
  for package caches; the cache speeds rebuilds without being stored in a
  layer.
- Combine `apt-get update` and `apt-get install` in one `RUN`, install with
  `--no-install-recommends`, and remove `/var/lib/apt/lists/*` in the same
  instruction.
- Start Dockerfiles with `# syntax=docker/dockerfile:1` to get current
  BuildKit frontend features (cache, secret, and SSH mounts).

## Build secrets

- Never pass credentials through `ARG` or `ENV`: both are recorded in image
  history and metadata. `docker history` and provenance attestations expose
  them.
- Use secret mounts: `RUN --mount=type=secret,id=npmrc,target=/root/.npmrc
  npm ci` with `docker buildx build --secret id=npmrc,src=$HOME/.npmrc`. The
  secret exists only for that instruction.
- Use `--mount=type=ssh` for private Git dependencies instead of copying keys.
- A secret copied into any layer remains recoverable even if a later layer
  deletes it. If that happened, rotate the secret and rebuild.

## Build context

- The `.dockerignore` file keeps VCS metadata, local secrets, environment
  files, dependency directories, and infrastructure state out of the context.
  Everything in the context can be copied by `COPY . .`.
- Prefer explicit `COPY src/ ./src/` over `COPY . .` in runtime stages.

## Reproducibility

- Pin base images by digest (`image:tag@sha256:...`). The tag documents intent;
  the digest guarantees content. Update digests through Dependabot or Renovate
  rather than by hand.
- Install dependencies from lockfiles with integrity checks
  (`pip install --require-hashes`, `npm ci`). Avoid `pip install <name>`
  without versions and `npm install` in images.
- Set `SOURCE_DATE_EPOCH` (BuildKit honors it for timestamps in image
  metadata and, with `rewrite-timestamp=true` on the exporter, for layer
  file timestamps) when byte-for-byte reproducible images are required.
- Record the source revision in OCI labels
  (`org.opencontainers.image.revision`, `.source`).

## Review checklist

- [ ] Final stage contains only runtime artifacts.
- [ ] Dependency layers precede source layers; caches use cache mounts.
- [ ] No credentials in `ARG`, `ENV`, `COPY`, or history; secret mounts used.
- [ ] `.dockerignore` excludes secrets, VCS data, and local build output.
- [ ] Base images pinned by digest; dependencies installed from lockfiles.

Templates: [Python Dockerfile](../assets/templates/Dockerfile.python.template),
[Node.js Dockerfile](../assets/templates/Dockerfile.node.template),
[.dockerignore](../assets/templates/dockerignore.template).

## Sources

- <https://docs.docker.com/build/building/multi-stage/>
- <https://docs.docker.com/build/building/best-practices/>
- <https://docs.docker.com/build/cache/optimize/>
- <https://docs.docker.com/build/building/secrets/>
- <https://docs.docker.com/build/concepts/context/#dockerignore-files>
- <https://docs.docker.com/build/ci/github-actions/reproducible-builds/>
- <https://github.com/opencontainers/image-spec/blob/main/annotations.md>
