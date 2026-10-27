# GitOps: push and pull deployment

Verified as of 2026-10-27 against the Flux and Argo CD documentation. Use this
reference only when the consumer runs Kubernetes; Container Apps and App
Service are deployed by the push workflows in this skill.

## Push versus pull

| Model | Who changes the environment | Credentials | Drift | Fits |
| --- | --- | --- | --- | --- |
| Push (CI/CD job calls the platform API) | the workflow | the workflow holds a deploy identity (OIDC) | not detected unless a separate check runs | PaaS targets, few environments |
| Pull (GitOps controller reconciles from a source) | a controller inside the cluster | the cluster reads the source; the pipeline only writes Git or OCI | detected and reverted continuously | Kubernetes fleets, many clusters |

In the pull model, desired state is declarative and version controlled, and a
controller continuously compares live state with it. Flux reconciles sources
(`GitRepository`, `OCIRepository`, `HelmRepository`, `Bucket`) into the cluster
through `Kustomization` and `HelmRelease` resources, every five minutes by
default for a `Kustomization`, and reverts manual `kubectl` edits. Argo CD
marks an application `OutOfSync` when live state deviates and can sync
automatically or on demand; it can track a branch, a tag, or a pinned commit.

## Promotion in a pull model

The same principle holds: build once, promote the digest.

1. CI builds and attests the image and records its digest.
2. A promotion job (or an image automation controller) opens a pull request
   that changes the image reference in the environment overlay to
   `name@sha256:...`. Review and required checks apply to that change.
3. Merging the pull request is the deployment for that environment; the
   controller applies it. Promotion to the next environment is another
   reviewed change to that environment's overlay.
4. Rollback is a revert commit; the controller restores the previous desired
   state. Do not edit the cluster by hand during an incident unless
   reconciliation is suspended, or the controller reverts the fix.

Flux also supports storing desired state as OCI artifacts in a registry
(Gitless GitOps), which removes the Git server from the runtime path and keeps
configuration, signatures, and images in one store.

Progressive delivery in the cluster is handled by Argo Rollouts or Flagger
(see `deployment-strategies.md`); the GitOps change sets the new digest and
the rollout controller moves traffic.

## Environment structure

- One overlay or values file per environment; the only difference between
  overlays is configuration and the promoted digest.
- Protect the environment paths with code owners so production changes need
  the production approvers, mirroring GitHub environment reviewers.
- Keep the controller's own configuration and access in infrastructure code
  reviewed with `kit-infra-review`.

## Drift detection

- Pull model: the controller reports drift continuously; alert when an
  application stays out of sync or reconciliation fails.
- Push model: schedule a read-only job that compares the running revision's
  image with the digest of the last successful deployment record and alerts on
  mismatch. Infrastructure drift (Terraform state, Azure resources) is checked
  by `kit-terraform-validation` and `kit-azure-validation` before each apply.

## Review checklist

- [ ] The overlays reference images by digest, never by tag.
- [ ] Promotion is a reviewed change per environment; rollback is a revert.
- [ ] Drift is detected and alerted in both pull and push setups.
- [ ] Manual cluster changes during incidents suspend reconciliation first
      and are recorded.

## Sources

- <https://fluxcd.io/flux/concepts/>
- <https://argo-cd.readthedocs.io/en/stable/>
- <https://argo-rollouts.readthedocs.io/en/stable/>
- <https://docs.flagger.app/>
