// Microsoft Entra built-in authentication: input type, guard and authConfigs properties.
import { isHostName, onlyChars } from './common.bicep'

@export()
@sealed()
type Authentication = {
  @description('Entra app registration (client) ID.')
  clientId: string
  @description('Entra tenant (directory) ID that issues the tokens.')
  tenantId: string
  @description('false (default): API mode, bearer tokens only, 401 without one. true: browser sign-in with ID tokens; no client secret.')
  signIn: bool?
  @description('Accepted token audiences besides the client ID, such as api://<clientId>.')
  allowedAudiences: string[]?
  @description('Lowercase public host name, without scheme, when users reach the app through an operator-owned edge or a custom domain.')
  publicHostName: string?
  @description('Absolute paths served without authentication, such as /health/ready for a post-deploy check.')
  excludedPaths: string[]?
}

func isGuid(value string) bool =>
  length(value) == 36 && onlyChars(value, '0123456789abcdefABCDEF-') && join(
    map(split(value, '-'), part => string(length(part))),
    ','
  ) == '8,4,4,4,12'

@export()
func requireAuthentication(settings Authentication?) Authentication? =>
  settings == null
    ? settings
    : isGuid(settings!.clientId) && isGuid(settings!.tenantId) && (settings!.?publicHostName == null
          ? true
          : isHostName(settings!.publicHostName!)) && empty(filter(
          settings!.?excludedPaths ?? [],
          path => !startsWith(path, '/') || contains(path, ' ')
        ))
        ? settings
        : fail('authentication needs GUID clientId and tenantId, publicHostName as a lowercase host name without scheme or path, and excludedPaths starting with /.')

// Without a client secret Easy Auth signs users in with an ID token only, so no credential is stored.
@export()
func authProperties(settings Authentication) object =>
  union(
    {
      platform: { enabled: true }
      globalValidation: union(
        (settings.?signIn ?? false)
          ? { unauthenticatedClientAction: 'RedirectToLoginPage', redirectToProvider: 'azureactivedirectory' }
          : { unauthenticatedClientAction: 'Return401' },
        empty(settings.?excludedPaths ?? []) ? {} : { excludedPaths: settings.?excludedPaths }
      )
      identityProviders: {
        azureActiveDirectory: union(
          {
            enabled: true
            registration: {
              clientId: settings.clientId
              #disable-next-line no-hardcoded-env-urls // Azure public cloud only, matching Terraform.
              openIdIssuer: 'https://login.microsoftonline.com/${settings.tenantId}/v2.0'
            }
          },
          empty(settings.?allowedAudiences ?? [])
            ? {}
            : { validation: { allowedAudiences: settings.?allowedAudiences } }
        )
      }
    },
    // Operator-owned edges and custom domains forward the public host in X-Forwarded-Host.
    settings.?publicHostName == null ? {} : { httpSettings: { forwardProxy: { convention: 'Standard' } } }
  )

// publicHostName wins; otherwise the caller passes the custom domain or the app FQDN. Null without browser sign-in.
@export()
func callbackUrl(settings Authentication?, appHostName string) string? =>
  (settings.?signIn ?? false) ? 'https://${settings.?publicHostName ?? appHostName}/.auth/login/aad/callback' : null
