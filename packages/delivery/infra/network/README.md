# Azure virtual network for private workloads (opt-in)

One application (spoke) virtual network carved from **one IPv4 prefix**:

- a subnet delegated to a Container Apps environment;
- a subnet for the private endpoints of the other compositions;
- one NSG per subnet;
- an explicit outbound (egress) path for the apps subnet: a NAT gateway, an
  existing route table, or the platform path;
- optionally, privatelink DNS zones linked to this VNet.

Choose **one** implementation: [Bicep](bicep/main.bicep) **or**
[Terraform](terraform/main.tf), never both over the same resources.

Vendor this directory from a reviewed immutable revision, retaining the delivery
package's MIT license/provenance. Use `bicep/main.bicep` as a resource-group-scoped
module or `terraform` as a local child module. The caller owns the resource group,
the IP address plan, hub connectivity, provider authentication, subscription
selection and Terraform state.

## Contract

Bicep uses camelCase; Terraform uses the corresponding snake_case.

| Input | Meaning |
| --- | --- |
| `location` | Required Azure region name, for example `westeurope` |
| `name` | Required VNet name: 2–64 letters, digits, underscores, periods or hyphens; also prefixes the NSGs and names each zone link |
| `stage` | Required `dev`, `test`, `staging` or `prod`; never inferred from a workspace |
| `resource_group_id` | Terraform only: required existing resource group ARM ID |
| `addressPrefix` | Required IPv4 network CIDR from `/16` to `/24`, for example `10.20.0.0/22`; host addresses, IPv6 and other lengths are rejected |
| `privateDnsZones` | Optional unique service keys from the zone table, default empty |
| `egress` | Optional `{ mode, routeTableId? }` (Terraform `{ mode, route_table_id }`): `platform`, `natGateway` or `routeTable`. Default: `natGateway` for `staging` and `prod`, `platform` for `dev` and `test` |

The subnets are derived from `addressPrefix` (`cidrSubnet` in Bicep,
`cidrsubnet` in Terraform):

| Subnet | Range | Example for `10.20.0.0/22` | Settings |
| --- | --- | --- | --- |
| `apps` | First half | `10.20.0.0/23` | Delegated to `Microsoft.App/environments`; NSG `<name>-apps-nsg` |
| `private-endpoints` | Third quarter | `10.20.2.0/24` | `privateEndpointNetworkPolicies: Enabled`, so NSGs apply to endpoints; NSG `<name>-pe-nsg` |
| None | Fourth quarter | `10.20.3.0/24` | Unallocated, reserved for growth |

Both subnets set `defaultOutboundAccess: false`. The NSGs have no custom rules:
the default rules deny inbound Internet traffic. A `/24` still gives the apps
subnet a `/25`, above the `/27` minimum for a workload-profiles environment.

| Key | Private DNS zone |
| --- | --- |
| `keyVault` | `privatelink.vaultcore.azure.net` |
| `redis` | `privatelink.redis.azure.net` |
| `postgresql` | `privatelink.postgres.database.azure.com` |
| `blob` | `privatelink.blob.core.windows.net` |
| `queue` | `privatelink.queue.core.windows.net` |
| `table` | `privatelink.table.core.windows.net` |
| `file` | `privatelink.file.core.windows.net` |
| `dfs` | `privatelink.dfs.core.windows.net` |
| `containerRegistry` | `privatelink.azurecr.io` |
| `search` | `privatelink.search.windows.net` |
| `cognitiveServices` | `privatelink.cognitiveservices.azure.com` |
| `openai` | `privatelink.openai.azure.com` |
| `aiServices` | `privatelink.services.ai.azure.com` |
| `cosmosDb` | `privatelink.documents.azure.com` |
| `containerApps` | `privatelink.<location>.azurecontainerapps.io` (lowercase, no spaces) |
| `monitor` | `privatelink.monitor.azure.com` (Azure Monitor Private Link Scope) |
| `oms` | `privatelink.oms.opinsights.azure.com` |
| `ods` | `privatelink.ods.opinsights.azure.com` |
| `agentsvc` | `privatelink.agentsvc.azure-automation.net` |

This is the single zone list for every private endpoint group the sibling
compositions create (`vault`, `redisEnterprise`, `postgresqlServer`, `blob`,
`registry`, `searchService`, `account`, `Sql`, `managedEnvironments`), plus the
other Storage sub-resources and the Azure Monitor Private Link Scope zones
(which also need `blob`). Bicep holds it in the `PrivateDnsZone` type and the
`zoneNames` map; Terraform holds it once in `local.zone_names` in `variables.tf`,
which the key validation and `main.tf` both read.

Zones are global resources in the caller's resource group, each linked to this
VNet with auto-registration off. Leave `privateDnsZones` empty in an enterprise
hub-and-spoke landing zone: the platform team owns these zones and links them
to the hub, and you pass its existing zone IDs to each module instead.

| Stage | Lock |
| --- | --- |
| `dev`, `test` | None |
| `staging` | None |
| `prod` | `CanNotDelete` on the VNet, on each zone this module creates, and on the NAT gateway and its public IP |

Outputs are `virtualNetworkResourceId`, `appsSubnetResourceId`,
`privateEndpointSubnetResourceId`, `privateDnsZoneResourceIds` (a map from
service key to zone ID that is empty by default), `egressMode` (the effective
mode) and `natGatewayPublicIpResourceId` (null unless the mode is
`natGateway`); snake_case in Terraform.

## Egress

The apps subnet sets `defaultOutboundAccess: false`, so it must have a
deliberate outbound path. A Container Apps environment needs outbound access to
pull images (for example `mcr.microsoft.com` and `*.data.mcr.microsoft.com`, or
your registry), to reach Microsoft Entra ID (`login.microsoftonline.com`) for
managed identity and authentication, and to reach Azure Monitor.

| Mode | Apps subnet | Use |
| --- | --- | --- |
| `natGateway` | Associated with `<name>-nat`, a Standard NAT gateway with one static Standard IPv4 address `<name>-nat-pip` | Deterministic, allow-listable outbound IP without a hub |
| `routeTable` | Associated with the existing `routeTableId`, for example a `0.0.0.0/0` user-defined route to a hub firewall | Hub-and-spoke landing zones; the hub owns the route table and firewall rules |
| `platform` | Neither | Relies on the outbound path Container Apps manages for a delegated subnet |

**Decision: NAT gateway by default for `staging` and `prod`, platform for
`dev` and `test`.** Production-like stages get an explicit, auditable outbound
path that keeps image pull and Entra sign-in working even if the platform-managed
path does not apply to a subnet without default outbound access. That
exemption for delegated PaaS subnets is documented by Azure but unverified here.
A NAT gateway and its public IP are billed hourly plus data processed, so the
default stays a cost toggle: set `egress: { mode: 'platform' }` to opt a
production-like stage out, or `{ mode: 'natGateway' }` to opt dev or test in.
In a hub-and-spoke landing zone, pass `{ mode: 'routeTable', routeTableId: ... }`
instead. A route to a firewall (next hop virtual appliance) takes precedence
over a NAT gateway, so don't combine them.

Firewall egress needs the Container Apps
[outbound FQDN allow list](https://learn.microsoft.com/en-us/azure/container-apps/firewall-integration),
plus your registry, Key Vault and other dependencies unless they are reached
through private endpoints. NAT gateway and user-defined routes need a
workload-profiles environment; the sibling container-apps composition creates one.

## Wiring

The outputs plug directly into the sibling compositions' inputs:

- Private endpoints (Key Vault, Managed Redis, PostgreSQL, Storage, Container
  Registry, AI Search, Document Intelligence, Cosmos DB, Container Apps): set
  `privateEndpoint.subnetId` to `privateEndpointSubnetResourceId` and
  `privateEndpoint.privateDnsZoneId` to `privateDnsZoneResourceIds.<key>`.
- AI Foundry: `privateEndpoint.privateDnsZoneIds` takes the
  `cognitiveServices`, `openai` and `aiServices` zone IDs.
- Container Apps environment: set `availability.infrastructureSubnetId` to
  `appsSubnetResourceId`.
- Terraform: for example `subnet_id = module.network.private_endpoint_subnet_resource_id`
  and `private_dns_zone_id = module.network.private_dns_zone_resource_ids["keyVault"]`.
- With hub-owned zones, pass the hub's zone IDs instead of `privateDnsZoneResourceIds`.

## Not included

These are platform (hub) responsibilities in a
[hub-spoke topology](https://learn.microsoft.com/en-us/azure/architecture/networking/architecture/hub-spoke):

- [VNet peering](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-network-peering-overview);
- [Azure Firewall](https://learn.microsoft.com/en-us/azure/firewall/overview) and the
  route tables that point to it (this module only associates an existing one);
- [DDoS Protection](https://learn.microsoft.com/en-us/azure/ddos-protection/ddos-protection-overview) plans;
- [VNet flow logs](https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview);
- custom DNS and
  [Private Link DNS at scale](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/ready/azure-best-practices/private-link-and-dns-integration-at-scale).

## Adoption

- Get `addressPrefix` from the organization's IP address management. It must not
  overlap the hub or any peered network. Address space and subnets are
  reviewed, not discovered.
- Workloads reach private endpoints only when their DNS resolves the privatelink
  zones. Without hub peering and DNS, CI runners and other VNets have no
  implicit access.
- Review the deployment and state with the selected owning tool before adoption.
  Inputs are not evidence of quota, address availability, DNS or permissions.

## Offline verification

From the repository root with installed tools and the existing Python environment:

```powershell
uv run --locked --no-sync pytest tests/integration/delivery/infra/test_network.py -q
task verify -- delivery
```

The tests relocate the complete source closure into temporary directories.

- Bicep: formatting, lint, compilation, the dev/prod examples, and the
  address/zone/egress guards with accepted and rejected inputs.
- Terraform: formatting, provider-free input tests, and cached-provider schema
  validation plus **mocked plans only**. Set `CONTAINER_APPS_AZAPI_MIRROR` to an
  existing local Azure/azapi 2.13.0 mirror to enable the full Terraform check.

Missing tools or a missing mirror are reported skips, not validation passes.
The tests do not download providers or use Azure account context.

Tool baseline: Bicep **0.39.26**, Terraform **1.11.3**; provider pin:
**Azure/azapi 2.13.0**. [REFERENCE.md](REFERENCE.md) records API pins, official
sources, limits, operator checks and rollback. A source revert cannot undo
existing infrastructure or state.
