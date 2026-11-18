func onlyChars(value string, alphabet string) bool =>
  empty(filter(range(0, length(value)), i => !contains(alphabet, substring(value, i, 1))))

// Reject embedded whitespace too; never repair a destination silently.
func hasWhitespace(value string) bool =>
  !empty(filter(range(0, length(value)), i => empty(trim(substring(value, i, 1)))))

// Each '*' segment must be non-empty; every other segment must match exactly (case-sensitive).
func matchesId(value string, pattern string) bool =>
  !hasWhitespace(value) && length(split(value, '/')) == length(split(pattern, '/'))
    ? empty(filter(
        range(0, length(split(pattern, '/'))),
        i =>
          split(pattern, '/')[i] == '*' ? empty(split(value, '/')[i]) : split(value, '/')[i] != split(pattern, '/')[i]
      ))
    : false

// One '@' with text on both sides and no whitespace; delivery is the operator's check.
func isEmail(value string) bool =>
  length(split(value, '@')) == 2 && !empty(first(split(value, '@'))) && !empty(last(split(value, '@'))) && !hasWhitespace(value)

// Exported guards are also evaluated offline by build-params in the tests.
@export()
func requireName(value string) string =>
  length(value) >= 2 && length(value) <= 32 && contains('abcdefghijklmnopqrstuvwxyz', first(value)) && contains(
      'abcdefghijklmnopqrstuvwxyz0123456789',
      last(value)
    ) && onlyChars(value, 'abcdefghijklmnopqrstuvwxyz0123456789-') && !contains(value, '--')
    ? value
    : fail('name must use 2-32 lowercase letters, digits or single hyphens; start with a letter and end alphanumeric.')

@export()
func requireContainerAppId(value string) string =>
  matchesId(value, '/subscriptions/*/resourceGroups/*/providers/Microsoft.App/containerApps/*')
    ? value
    : fail('containerAppResourceId must be a Microsoft.App/containerApps ARM ID.')

@export()
func requireActionGroup(id string?) string? =>
  id == null
    ? null
    : matchesId(id!, '/subscriptions/*/resourceGroups/*/providers/Microsoft.Insights/actionGroups/*')
        ? id
        : fail('existingActionGroupResourceId must be an action group ARM ID.')

// Exactly one destination: emails, an existing group, or (dev/test only) unmonitored.
@export()
func requireEmailReceivers(stage string, addresses string[], groupId string?, unmonitored bool) string[] =>
  !empty(filter(addresses, address => !isEmail(address)))
    ? fail('emailReceivers must be email addresses, for example ops@example.com.')
    : unmonitored && contains(['staging', 'prod'], stage)
        ? fail('unmonitored is allowed only for dev and test; staging and production require emailReceivers or existingActionGroupResourceId.')
        : (empty(addresses) ? 0 : 1) + (groupId == null ? 0 : 1) + (unmonitored ? 1 : 0) > 1
            ? fail('emailReceivers, existingActionGroupResourceId and unmonitored are mutually exclusive; set exactly one.')
            : empty(addresses) && groupId == null && !unmonitored
                ? fail(contains(['staging', 'prod'], stage)
                    ? 'Staging and production require emailReceivers or existingActionGroupResourceId.'
                    : 'Set exactly one of emailReceivers, existingActionGroupResourceId or unmonitored=true.')
                : addresses

@description('Prefix for the action group and alert rule names. Use a distinct prefix per stage.')
@minLength(2)
@maxLength(32)
param namePrefix string

@allowed(['dev', 'test', 'staging', 'prod'])
param stage string

@description('ARM ID of the existing Container App to watch.')
param containerAppResourceId string

@description('Email addresses for a managed action group. Mutually exclusive with existingActionGroupResourceId and unmonitored.')
param emailReceivers string[] = []

@description('Caller-owned action group ARM ID, for example one with a Teams workflow receiver. Its receivers are never read or managed. Mutually exclusive with emailReceivers and unmonitored. Omit (null) when unused; an empty string is rejected.')
@minLength(1)
param existingActionGroupResourceId string?

@description('Explicit opt-out for dev and test only: the rules exist but notify nobody. Rejected for staging and prod.')
param unmonitored bool = false

// Alert policy, named once and shared by both rules. Severity 2 is Warning (0 is Critical, 4 Verbose).
var alertSeverity = 2
// Evaluate every minute over a sliding five-minute window (ISO 8601 durations).
var evaluationFrequency = 'PT1M'
var windowMinutes = 5
var windowSize = 'PT${windowMinutes}M'
// RestartCount is cumulative per replica: more than this many restarts is a crash loop.
var restartThreshold = 3
var serverErrorThreshold = 5

var prefix = requireName(namePrefix)
var appId = requireContainerAppId(containerAppResourceId)
var existingGroupId = requireActionGroup(existingActionGroupResourceId)
var emails = requireEmailReceivers(stage, emailReceivers, existingGroupId, unmonitored)
// Null when unmonitored; the rules then notify nobody.
var notificationGroupId = !empty(emails) ? notify!.id : existingGroupId
var alertActions = unmonitored ? [] : [{ actionGroupId: notificationGroupId }]
var tags = { stage: stage }

// Only non-defaults are declared: email keeps the default schema. Teams is configured
// by the operator inside a caller-owned action group (see REFERENCE.md).
resource notify 'Microsoft.Insights/actionGroups@2023-01-01' = if (!empty(emails)) {
  name: '${prefix}-notify'
  location: 'global'
  tags: tags
  properties: {
    // Shown in SMS and email; at most 12 characters.
    groupShortName: take(prefix, 12)
    // Required by this API version.
    enabled: true
    emailReceivers: map(emails, (address, i) => { name: 'email-${i}', emailAddress: address })
  }
}

// RestartCount is cumulative per replica, so its maximum exposes a crash loop.
resource restarts 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${prefix}-restarts'
  location: 'global'
  tags: tags
  properties: {
    description: 'A replica restarted more than ${restartThreshold} times: crash loop or failing probes.'
    severity: alertSeverity
    // Required by this API version.
    enabled: true
    // Stated explicitly: the alert resolves itself when the condition clears.
    autoMitigate: true
    scopes: [appId]
    evaluationFrequency: evaluationFrequency
    windowSize: windowSize
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'restarts'
          metricName: 'RestartCount'
          timeAggregation: 'Maximum'
          operator: 'GreaterThan'
          threshold: restartThreshold
        }
      ]
    }
    actions: alertActions
  }
}

// Needs HTTP ingress; an app without ingress emits no Requests.
resource serverErrors 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: '${prefix}-5xx'
  location: 'global'
  tags: tags
  properties: {
    description: 'More than ${serverErrorThreshold} HTTP 5xx responses in ${windowMinutes} minutes.'
    severity: alertSeverity
    // Required by this API version.
    enabled: true
    // Stated explicitly: the alert resolves itself when the condition clears.
    autoMitigate: true
    scopes: [appId]
    evaluationFrequency: evaluationFrequency
    windowSize: windowSize
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion'
          name: 'server-errors'
          metricName: 'Requests'
          dimensions: [{ name: 'statusCodeCategory', operator: 'Include', values: ['5xx'] }]
          timeAggregation: 'Total'
          operator: 'GreaterThan'
          threshold: serverErrorThreshold
        }
      ]
    }
    actions: alertActions
  }
}

@description('Action group ARM ID (created or caller-owned); null when unmonitored. Reuse it for further alert rules on the same app.')
output actionGroupId string? = notificationGroupId
