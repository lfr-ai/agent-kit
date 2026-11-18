// Container App inputs: image, identity, registry, secrets, environment, telemetry and resource guards.
import { onlyChars } from './common.bicep'

@export()
@sealed()
type SecretReference = {
  name: string
  environmentVariable: string
  keyVaultUrl: string
}

@export()
type EnvironmentVariables = {
  *: string
}

// Exported guards are also evaluated offline by build-params in the tests.
@export()
func requireDigest(image string) string =>
  length(split(image, '@sha256:')) == 2 && contains(first(split(image, '@sha256:')), '/') && onlyChars(
      first(split(image, '@sha256:')),
      'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/:-'
    ) && length(last(split(image, '@sha256:'))) == 64 && onlyChars(last(split(image, '@sha256:')), '0123456789abcdef')
    ? image
    : fail('containerImage must be a registry/repository@sha256: followed by 64 lowercase hex digits.')

@export()
func requireName(value string) string =>
  length(value) >= 2 && length(value) <= 32 && contains('abcdefghijklmnopqrstuvwxyz', first(value)) && contains(
      'abcdefghijklmnopqrstuvwxyz0123456789',
      last(value)
    ) && onlyChars(value, 'abcdefghijklmnopqrstuvwxyz0123456789-') && !contains(value, '--')
    ? value
    : fail('Names must use 2-32 lowercase letters, digits or single hyphens; start with a letter and end alphanumeric.')

// Null means absent. The ternaries compile to if(), which ARM evaluates lazily, so null never reaches a string check.
@export()
func requireIdentity(value string?, needsAccess bool) string? =>
  value == null
    ? needsAccess
        ? fail('Key Vault, ACR and Application Insights require a pre-authorized user-assigned managed identity ARM ID.')
        : value
    : startsWith(value!, '/subscriptions/') && contains(value!, '/resourceGroups/') && contains(
          value!,
          '/providers/Microsoft.ManagedIdentity/userAssignedIdentities/'
        ) && length(split(value!, '/')) == 9 && !empty(last(split(value!, '/')))
        ? value
        : fail('Key Vault, ACR and Application Insights require a pre-authorized user-assigned managed identity ARM ID.')

@export()
func requireRegistry(server string?, image string) string? =>
  server == null
    ? server
    : endsWith(server!, '.azurecr.io') && onlyChars(server!, 'abcdefghijklmnopqrstuvwxyz0123456789.-') && startsWith(
          image,
          '${server!}/'
        )
        ? server
        : fail('Private ACR requires its matching azurecr.io image and a login server without scheme.')

func isKeyVaultUrl(value string) bool =>
  #disable-next-line no-hardcoded-env-urls // Input validation is intentionally restricted to Azure public cloud, matching Terraform.
  startsWith(value, 'https://') && endsWith(split(value, '/')[2], '.vault.azure.net') && length(split(
    split(value, '/')[2],
    '.'
  )) == 4 && !empty(first(split(split(value, '/')[2], '.'))) && onlyChars(
    split(value, '/')[2],
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-'
  ) && contains(value, '/secrets/') && contains([5, 6], length(split(value, '/'))) && !empty(split(value, '/')[4]) && onlyChars(
    split(value, '/')[4],
    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'
  ) && (length(split(value, '/')) == 5 || (length(last(split(value, '/'))) == 32 && onlyChars(
    last(split(value, '/')),
    '0123456789abcdefABCDEF'
  )))

@export()
func requireSecrets(refs SecretReference[]) SecretReference[] =>
  empty(intersection(map(refs, ref => toUpper(ref.environmentVariable)), reservedNames())) && length(toObject(
      refs,
      ref => ref.name
    )) == length(refs) && length(toObject(refs, ref => toUpper(ref.environmentVariable))) == length(refs) && empty(filter(
      refs,
      ref =>
        empty(ref.name) || length(ref.name) > 253 || !contains('abcdefghijklmnopqrstuvwxyz0123456789', first(ref.name)) || !onlyChars(
          ref.name,
          'abcdefghijklmnopqrstuvwxyz0123456789-'
        ) || empty(ref.environmentVariable) || !contains(
          'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_',
          first(ref.environmentVariable)
        ) || !onlyChars(ref.environmentVariable, 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_') || !isKeyVaultUrl(ref.keyVaultUrl)
    ))
    ? refs
    : fail('Use unique, non-reserved secret/environment names and HTTPS Key Vault secret URLs; never secret values.')

// Always reserved, ignoring case: telemetry names, so enabling telemetry cannot introduce
// duplicates, and the Azure Identity credential overrides, which would make
// DefaultAzureCredential pick a client secret, certificate or federated token before the
// managed identity.
func reservedNames() string[] => [
  'OTEL_SERVICE_NAME'
  'OTEL_RESOURCE_ATTRIBUTES'
  'APPLICATIONINSIGHTS_CONNECTION_STRING'
  'AZURE_CLIENT_ID'
  'OTEL_EXPORTER_OTLP_ENDPOINT'
  'OTEL_EXPORTER_OTLP_PROTOCOL'
  'AZURE_CLIENT_SECRET'
  'AZURE_CLIENT_CERTIFICATE_PATH'
  'AZURE_FEDERATED_TOKEN_FILE'
]

@export()
func requireEnvironment(values EnvironmentVariables, secretVariables string[]) EnvironmentVariables =>
  empty(filter(
      items(values),
      entry =>
        empty(entry.key) || !contains('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_', first(entry.key)) || !onlyChars(
          entry.key,
          'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'
        )
    )) && length(toObject(items(values), entry => toUpper(entry.key))) == length(items(values)) && empty(intersection(
      map(items(values), entry => toUpper(entry.key)),
      map(secretVariables, name => toUpper(name))
    )) && empty(intersection(
      map(items(values), entry => toUpper(entry.key)),
      concat(
        reservedNames(),
        ['APP_POSTGRES_PASSWORD', 'APP_REDIS_URL', 'APP_AI_API_KEY', 'OTEL_EXPORTER_OTLP_HEADERS']
      )
    ))
    ? values
    : fail('environmentVariables requires valid nonsecret names unique across secretReferences, ignoring case, without reserved telemetry or credential-override names; credential slots require Key Vault references.')

@export()
func requireTelemetry(connectionString string?, otlpEndpoint string?, secretVariables string[]) bool =>
  (connectionString == null ? true : contains(connectionString!, 'InstrumentationKey=')) && (otlpEndpoint == null
      ? true
      : startsWith(otlpEndpoint!, 'https://')) && (connectionString == null && otlpEndpoint == null
      ? true
      : empty(intersection(map(secretVariables, name => toUpper(name)), reservedNames())))
    ? connectionString != null || otlpEndpoint != null
    : fail('applicationInsightsConnectionString needs InstrumentationKey=, otlpEndpoint needs https://, and secretReferences must not set the variables telemetry sets.')

// Consumption workload profile: 0.25 to 4 vCPU in 0.25 steps, always with twice as many GiB.
func resourcePairs() object => {
  '0.25': '0.5Gi'
  '0.5': '1Gi'
  '0.75': '1.5Gi'
  '1': '2Gi'
  '1.25': '2.5Gi'
  '1.5': '3Gi'
  '1.75': '3.5Gi'
  '2': '4Gi'
  '2.25': '4.5Gi'
  '2.5': '5Gi'
  '2.75': '5.5Gi'
  '3': '6Gi'
  '3.25': '6.5Gi'
  '3.5': '7Gi'
  '3.75': '7.5Gi'
  '4': '8Gi'
}

// cpu is a decimal string because Bicep has no floats; the caller converts it with json().
@export()
func requireResources(cpu string, memory string) string =>
  contains(resourcePairs(), cpu) && resourcePairs()[cpu] == memory
    ? cpu
    : fail('cpu and memory must be a Consumption pair: cpu 0.25 to 4 in 0.25 steps with memory twice the cpu in Gi, such as 0.5 and 1Gi.')
