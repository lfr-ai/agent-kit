# Variables, conditions, and terraform test

## Variables

- Declare `type` and `description` for every variable. Use object types with
  `optional()` attributes instead of untyped maps for structured input.
- Set `nullable = false` when `null` would break the configuration.
- Add `validation` blocks for every constraint the cloud API enforces late
  (name patterns, allowed values, ranges). Since Terraform 1.9 a condition may
  reference other variables, so cross-field rules (for example "prod must not
  use LRS") are expressed where the input is declared.
- Mark secret inputs `sensitive = true` to redact them from CLI output. This
  does not keep them out of state; use `ephemeral = true` (1.10+) when the
  value is only needed during the run.
- Keep non-secret per-environment values in committed `.tfvars` files; inject
  secrets at runtime from a vault or pipeline secret store.

## Custom conditions

| Construct | Runs | Failure effect | Use for |
| --- | --- | --- | --- |
| `variable` `validation` | Before plan | Error | Input shape and allowed values |
| `precondition` | Before resource create/update | Error | Assumptions about inputs or data sources |
| `postcondition` | After resource create/update | Error | Guarantees the provider must deliver |
| `check` block `assert` | Every plan and apply | Warning | Ongoing health or drift signals |
| `output` `precondition` | Before output is set | Error | Contract with callers |

Write error messages that state the rule and the fix, not only the failure.

## terraform test

`terraform test` (1.6+) executes `*.tftest.hcl` files from the module root or
its `tests/` directory. Each `run` block executes `plan` or `apply` against
the module and evaluates `assert` blocks.

- Prefer `command = plan` with `mock_provider` (1.7+) for unit tests: no
  credentials, no cost, deterministic. Mocked computed attributes get
  synthetic values; attributes set in configuration keep their real values.
- Use `override_resource`, `override_data`, or `override_module` to pin
  specific computed values that assertions depend on.
- Assert negative cases with `expect_failures = [var.name]` or a resource
  address whose precondition must fail. A negative test passes only when the
  listed checkable objects fail and nothing else does.
- Reserve `command = apply` against real providers for integration tests in a
  sandbox subscription; tests destroy what they create, in reverse order, but
  a failed teardown leaves resources behind, so run them under a disposable
  scope with budget alerts.
- Variables set in a file-level `variables` block apply to every run; a run's
  own `variables` block overrides them.
- Run root tests with `terraform init -backend=false` so tests never touch
  remote state.

## Review checklist

- [ ] Every variable has a type, description, and validation where the API
      has constraints.
- [ ] Secrets are `sensitive` or `ephemeral` and never have defaults.
- [ ] Each module has plan-mode tests for its secure defaults and at least one
      `expect_failures` test per validation rule.
- [ ] Tests run offline with mock providers in CI.

Templates: [variables.tf](../assets/blueprint/variables.tf.template),
[storage module tests](../assets/blueprint/modules/storage/tests/storage.tftest.hcl.template),
[root tests](../assets/blueprint/tests/main.tftest.hcl.template).

## Sources

- <https://developer.hashicorp.com/terraform/language/values/variables>
- <https://developer.hashicorp.com/terraform/language/expressions/custom-conditions>
- <https://developer.hashicorp.com/terraform/language/checks>
- <https://developer.hashicorp.com/terraform/language/tests>
- <https://developer.hashicorp.com/terraform/language/tests/mocking>
- <https://developer.hashicorp.com/terraform/cli/commands/test>
