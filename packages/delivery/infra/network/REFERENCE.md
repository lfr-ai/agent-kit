# Virtual network: operator gates, evidence and rollback

Start with the [module contract](README.md).

## Defaults this composition relies on

The sources declare only what differs from the platform default, plus values
the API requires:

- `defaultOutboundAccess: false` is explicit. Until API versions released after
  2026-03-31, new subnets default to `true`, which gives VMs an implicit public
  outbound IP. Azure documents that private subnets don't apply to delegated
  subnets that host PaaS services, so on `apps` Container Apps would manage its
  own outbound path. That is unverified live, so `staging` and `prod` default
  to a NAT gateway (see the README egress decision); `platform` mode relies on
  the exemption.
- The NAT public IP is Standard, Static and IPv4 with no `zones`, because a
  Standard NAT gateway is zonal or no-zone and must match its IP. It is not
  zone-redundant: a zonal outage can interrupt egress. The NAT idle timeout
  keeps its API default (4 minutes).
- `privateEndpointNetworkPolicies: Enabled` is explicit because the API default
  is `Disabled`. Without it the subnet NSG and route tables don't apply to
  private endpoint traffic.
- `registrationEnabled: false` is explicit on each zone link; the template
  reference documents no default.
- The NSGs have no rules. The default rules allow inbound from the VNet and
  Azure Load Balancer, deny other inbound, and allow outbound. That covers
  traffic from the private endpoint subnet to the Container Apps environment and
  the load balancer probes. For a workload-profiles environment that accepts
  public traffic, that traffic arrives on the platform's public endpoint, not
  through the subnet, so this NSG neither needs nor applies an inbound rule for it.

Omitted defaults are not a drift-remediation guarantee. Enforce organizational
network requirements with Azure Policy and post-deployment checks.

## Operator gates and ownership

- Keep one IaC owner. Terraform has no backend, provider configuration, data
  sources or account discovery; the caller explicitly supplies authentication,
  subscription, resource group and state. Bicep runs at resource-group scope.
  Never apply the other implementation to resources already owned by one tool
  without reviewed import/state migration.
- Subnets are declared inline in the VNet, so a later update of this module never
  deletes them. A subnet added to this VNet outside the module is removed by the
  next apply, or the apply fails if that subnet is in use. Add subnets here, in
  a reviewed change, or use a separate VNet.
- The address guard checks the syntax, the `/16`–`/24` range, and that the
  prefix is a network address. It does not check for overlap with the hub,
  peered VNets or on-premises ranges. Changing `addressPrefix` later resizes
  both subnets, which Azure rejects while a subnet is in use, so treat the
  prefix as fixed.
- Bicep rejects an unknown zone key at compile time through its type, and
  rejects duplicates through the shared guard. Terraform rejects both through
  variable validation. Bicep checks the VNet name length; ARM checks its
  characters. Terraform also rejects invalid VNet names locally.
- The deployer needs rights to create VNets, NSGs, private DNS zones and links,
  and to write locks in the resource group. Joining a subnet from another
  module needs `Microsoft.Network/virtualNetworks/subnets/join/action`.
  Resource-provider registration is an operator check; nothing is registered or
  logged in automatically.
- The Container Apps zone name uses the lowercased location with spaces removed,
  the same normalization as the container-apps guard. Pass the region name
  (`westeurope`), not an alias that Azure would map elsewhere.
- Created zones serve only this VNet. Linking the same zone name elsewhere
  creates a split-brain DNS view. In a landing zone, let the platform team own
  the zones and leave `privateDnsZones` empty.
- The production `CanNotDelete` lock on the VNet is inherited by everything
  under it, including subnets and their service association links. It does not
  block creating or updating resources. Offline tests can't show whether it
  blocks deleting a Container Apps environment or private endpoint on these
  subnets. Rehearse those deletions against a locked VNet before relying on
  them, or plan an approved unlock first. Azure documents that VNet-integrated
  PostgreSQL flexible servers need VNet and subnet locks removed before
  creation. The sibling PostgreSQL composition uses a private endpoint instead.
- A production zone lock is inherited by the zone's links and record sets.
  Private endpoint DNS zone groups can still add records. Removing a record,
  which happens when an endpoint or its zone group is deleted, may be blocked
  or leave a stale record; this is unverified offline. Nobody can delete the
  zone without first removing the lock.
- Associating a NAT gateway or route table with the apps subnet updates the
  subnet in place. Whether Azure accepts this while a Container Apps environment
  already uses the subnet is unverified offline; rehearse the switch, or set
  `egress` before the environment is created. Switching from `natGateway` to
  another mode changes the outbound IP, and Terraform deletes the NAT gateway
  and its IP (production first needs their locks removed). A changed IP breaks
  downstream allow-lists.
- `routeTable` only associates an existing route table; the egress guard checks
  that the ID names a `Microsoft.Network/routeTables` resource. The deployer
  needs `Microsoft.Network/routeTables/join/action` on it, and the firewall must
  allow the Container Apps outbound FQDNs. Route table contents and firewall
  rules are hub responsibilities.
- An NSG can't be deleted while it is associated with a subnet. The Terraform
  zone locks depend on the zone links, so creation puts the lock last and
  reverse destroy removes it first.

## Offline evidence and limitations

The integration test copies byte-identical sources away from the checkout.
Installed Bicep **0.39.26** checks format, lint, build and parameter compilation.
The exported address and zone guards are evaluated with accepted and rejected
inputs, and an unknown zone key must fail type checking. Compiled ARM assertions
check the subnet expressions, delegation, NSG associations, zone links and
resource-scoped locks.

Terraform checks formatting and runs input-contract tests against the
unchanged `variables.tf` without a provider (it holds the zone list as a local
so the key validation reads the same list as `main.tf`). Full `validate` and the fourteen
`terraform test` runs require the existing local **Azure/azapi 2.13.0** mirror
named by `CONTAINER_APPS_AZAPI_MIRROR`. Initialization uses
`-backend=false -input=false -get=false -plugin-dir=<mirror>` only in the
temporary copy; provider downloads, backend access and account discovery are
not permitted. AzAPI's embedded schema validation runs during `validate` and
accepts every declared property, including `defaultOutboundAccess`, for the
pinned VNet API.

All resource tests use `mock_provider "azapi"` and `command = plan`, with
synthetic IDs overridden during plan. They assert the following:

- subnet math for `/16`, `/22` and `/24`;
- the delegation, NSG associations, endpoint policies and outbound setting;
- the zone set and Container Apps zone normalization;
- the stage-derived egress default, NAT gateway and public IP bodies, the apps
  subnet association, route-table egress and an explicit platform opt-out;
- zone links;
- production locks;
- the outputs;
- rejection of bad prefixes, unknown keys, duplicate keys and a route-table
  mode without an ID.

No test applies resources. Missing tools or a missing mirror produce explicit
skips. The tests were run with Terraform 1.16.7; the 1.11.3 baseline is the
declared minimum, not separately exercised here.

API pins:

| Resources | API version |
| --- | --- |
| Virtual network, subnets, NSGs | `2025-01-01` |
| Public IP address, NAT gateway | `2025-01-01` |
| Private DNS zones and virtual network links | `2024-06-01` |
| Resource lock | `2020-05-01` |

These are offline source, schema and mocked-plan checks, not Azure service
certification. Live behavior of the following needs an explicitly authorized
operator session later:

- address availability and quotas;
- Container Apps acceptance of the delegated subnet with these settings;
- image pull and Entra sign-in through each egress mode, especially
  `platform` with `defaultOutboundAccess: false`;
- NAT gateway or route table association on a subnet already in use;
- deletion under locks;
- Azure Policy, DNS resolution and RBAC.

## Rollback

This change performs no deployment and changes no cloud or Terraform state.
To undo it, delete this directory and `tests/integration/delivery/infra/test_network.py`.
Remove the `network` entries from `COMPOSITIONS` and `AZURE_COMPOSITIONS`, then
regenerate the delivery catalog from the reviewed owning sources.

After adoption, revert inputs through the owning IaC tool and review its plan.
Do not delete the module from state or switch implementations as a rollback.

- Removing a zone key makes Terraform delete the zone and every record in it;
  production first needs its lock removed in an approved change. Endpoints that
  relied on the zone stop resolving privately.
- Bicep incremental mode leaves removed zones, links and locks in place; delete
  them explicitly if intended. The same applies to a NAT gateway and public IP
  after switching away from `natGateway`, although the subnet association is
  removed because subnets are declared inline.
- A released NAT public IP address cannot be recovered; allow-lists that used
  it must be updated.
- The VNet cannot be deleted while Container Apps environments or private
  endpoints still use its subnets. Remove those first, through their owners.

Source reverts do not restore deleted DNS records, re-create deleted private
endpoints, or restore lost Terraform state.

## Official sources

Reviewed on 2026-11-12 (public Azure documentation only):

- [Virtual network API](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/virtualnetworks)
  and [network security group API](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/networksecuritygroups).
- [Private DNS zone API](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2024-06-01/privatednszones)
  and [virtual network link API](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2024-06-01/privatednszones/virtualnetworklinks).
- [Private endpoint DNS zone values](https://learn.microsoft.com/en-us/azure/private-link/private-endpoint-dns).
- [Private endpoint network policies](https://learn.microsoft.com/en-us/azure/private-link/disable-private-endpoint-network-policy).
- [Default outbound access](https://learn.microsoft.com/en-us/azure/virtual-network/ip-services/default-outbound-access).
- [NAT gateway](https://learn.microsoft.com/en-us/azure/nat-gateway/nat-overview),
  [NAT gateway API](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/natgateways)
  and [public IP address API](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/2025-01-01/publicipaddresses).
- [Network security groups](https://learn.microsoft.com/en-us/azure/virtual-network/network-security-groups-overview).
- [Container Apps virtual networks](https://learn.microsoft.com/en-us/azure/container-apps/custom-virtual-networks)
  and [Container Apps NSG rules](https://learn.microsoft.com/en-us/azure/container-apps/firewall-integration).
- [PostgreSQL private networking](https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private).
- [Resource locks](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/lock-resources).
- [Bicep CIDR functions](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/bicep-functions-cidr)
  and [Terraform `cidrsubnet`](https://developer.hashicorp.com/terraform/language/functions/cidrsubnet).
