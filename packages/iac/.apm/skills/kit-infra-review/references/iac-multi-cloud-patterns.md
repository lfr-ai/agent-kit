# Multi-cloud patterns

Multi-cloud infrastructure stays reviewable when each root module is small,
owned by one team, and targets one cloud boundary. Facts checked 2026-10.

## Root module per boundary

Create one root module (one state, one preview, one apply) per combination of:

- cloud account boundary: AWS account, Azure subscription, Google Cloud
  project or folder;
- environment: dev, test, prod;
- layer: organization and landing zone, shared platform, workload.

```text
infra/
  aws/
    platform/prod/      # one state: network and logging in the prod account
    orders/prod/        # one state: workload stack in the same account
  azure/
    orders/prod/
  gcp/
    analytics/prod/
  modules/              # reusable child modules, one cloud each
```

Why: a smaller state bounds blast radius, keeps plans fast and readable, and
lets each identity hold only the permissions for its boundary. A single root
module spanning clouds forces one identity to hold every cloud's write access
and makes one provider outage block every change.

## Provider configuration

- Configure providers only in root modules. Pass alternates to child modules
  with `providers = { aws.replica = aws.replica }` and declare them in the
  module with `configuration_aliases`.
- Use aliases for a second Region or account inside the same boundary (for
  example a replica bucket or a DNS zone in a shared account), not to reach
  into another team's environment.
- OpenTofu 1.9 and later accept `for_each` on provider configurations, which
  reduces repetition for many Regions; Terraform does not, so a module using
  it is OpenTofu-only.
- Pin each provider with a pessimistic constraint (`~> 6.0`) and commit the
  lock file; upgrade providers one cloud at a time.

## No lowest-common-denominator modules

Do not write a `bucket` or `network` module that hides whether it creates an
S3 bucket, a storage account, or a Cloud Storage bucket. Each cloud differs in
identity, encryption, network isolation, replication, and naming rules; an
abstraction either exposes only what all clouds share (losing security
controls) or grows a flag for every difference (becoming harder to review
than three plain modules).

Instead:

- write one module per cloud with that cloud's secure defaults;
- share a small contract: the same input names for `environment`, `workload`,
  and owner metadata, and the same output names for identifiers consumers need;
- share policy and naming rules as data (a locals file or a policy bundle),
  not as code that branches on cloud.

## Sharing values between stacks

| Mechanism | Use when | Caution |
| --- | --- | --- |
| Outputs read by `terraform_remote_state` | Same tool, consumer may read the producer's state | Grants read access to the whole state, including sensitive values |
| Cloud-native lookup (`data` sources by name or tag) | Consumer can discover the resource itself | Couples consumer to naming; fails if the resource is missing |
| Parameter store (AWS SSM Parameter Store, Azure App Configuration, Google Secret Manager or Parameter Manager) | Several tools or teams consume the value | Producer must write it; treat as an interface with an owner |
| CI outputs passed between jobs | Values are only needed in one pipeline run | Not durable; do not use for long-lived contracts |

Prefer published values (outputs written to a parameter store, or a narrow
data lookup) over `terraform_remote_state`, which exposes every attribute in
the producer's state.

## Naming, tags, and labels

- Use one naming pattern across clouds, such as
  `<workload>-<environment>-<region-short>-<instance>`, and adapt it per cloud
  where rules differ (length limits, global uniqueness, allowed characters).
- Azure storage accounts and Google Cloud Storage and S3 bucket names are
  globally unique; add an instance or random suffix.
- Apply the same metadata keys everywhere: `owner`, `environment`,
  `cost_center`, `workload`, `managed_by`.
- AWS: set `default_tags` in the provider so every taggable resource gets them.
- Google Cloud: set `default_labels` in the provider. Label keys and values
  allow only lowercase letters, digits, underscores, and dashes, up to 63
  characters, with at most 64 labels per resource, so normalize values.
- Azure: tags are not inherited from resource groups by default; set them on
  every resource or use Azure Policy to inherit and require them.

## Landing zones (account and subscription vending)

Do not hand-build organization structure in each workload repository. Adopt
the cloud's landing zone reference, owned by a platform team, and treat it as
its own layer:

| Cloud | Reference implementations | Tooling |
| --- | --- | --- |
| Azure | Azure landing zones (Cloud Adoption Framework) built from Azure Verified Modules, including the `avm-ptn-alz` pattern module | Terraform or Bicep accelerators |
| AWS | AWS Control Tower with Account Factory for Terraform (AFT), or Landing Zone Accelerator on AWS | Control Tower, CloudFormation and CDK, Terraform for AFT |
| Google Cloud | Cloud Foundation Fabric and the Terraform example foundation | Terraform, optionally run by Infrastructure Manager |

Workload root modules consume the landing zone through published outputs
(subscription or account identifiers, network identifiers, log destinations)
and never modify landing zone resources.

## Identity for automation

- One federated identity per boundary and purpose: a read-scoped identity for
  plan and preview, a separate identity for apply bound to a protected
  environment. Configure federation per cloud; pipeline mechanics belong to
  `kit-delivery-pipelines`.
- No long-lived keys in CI. Each cloud's GitHub OIDC integration exchanges the
  workflow token for short-lived credentials.

## Review checklist

- [ ] Each root module targets one cloud boundary, one environment, one layer.
- [ ] Providers are configured only in root modules and pinned.
- [ ] Modules are cloud-specific; shared contracts are inputs, outputs, data.
- [ ] Cross-stack values flow through published outputs, not shared state.
- [ ] Naming and metadata rules are written down and validated per cloud.
- [ ] Landing zone resources are owned by one platform layer.

## Sources

- <https://developer.hashicorp.com/terraform/language/modules/develop/providers>
- <https://developer.hashicorp.com/terraform/language/state/remote-state-data>
- <https://opentofu.org/docs/language/providers/configuration/>
- <https://registry.terraform.io/providers/hashicorp/aws/latest/docs#default_tags-configuration-block>
- <https://registry.terraform.io/providers/hashicorp/google/latest/docs/guides/provider_reference>
- <https://cloud.google.com/resource-manager/docs/labels-overview>
- <https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/tag-resources>
- <https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/landing-zone/>
- <https://azure.github.io/Azure-Landing-Zones/>
- <https://azure.github.io/Azure-Verified-Modules/>
- <https://docs.aws.amazon.com/controltower/latest/userguide/aft-overview.html>
- <https://docs.aws.amazon.com/solutions/latest/landing-zone-accelerator-on-aws/solution-overview.html>
- <https://github.com/GoogleCloudPlatform/cloud-foundation-fabric>
- <https://github.com/terraform-google-modules/terraform-example-foundation>
