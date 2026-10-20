---
name: kit-browser-tests
description: Use when adding stable browser-level tests for user workflows and cross-component behavior.
license: MIT
---

# Test the browser-visible contract

## Resources

- [Browser-test guide](references/guide.md): prerequisites and recovery gates.
- [Playwright patterns](references/playwright-patterns.md): scope, locators,
  waiting, isolation, network control, evidence, CI, anti-patterns.
- [Flake triage](references/flake-triage.md): reproduce, classify with traces,
  time control, fix order, quarantine rules.
- [Journey contract](assets/journey-contract.md) to fill per journey.
- Templates: [config](assets/playwright.config.ts.template),
  [auth setup](assets/auth.setup.ts.template),
  [page object](assets/orders.page.ts.template),
  [fixtures](assets/fixtures.ts.template),
  [journey spec](assets/orders.spec.ts.template),
  [accessibility spec](assets/accessibility.spec.ts.template).

## Procedure

1. Read the guide; fill the journey contract before writing the test.
2. Select a critical journey that crosses routing, rendering, and a real boundary;
   keep cheaper validation in unit and component tests.
3. Use the project's installed runner against a production build and isolated
   test data; never depend on a live account.
4. Locate controls by role and accessible name; wrap them in page objects.
5. Wait with web-first assertions on visible state, never fixed sleeps.
6. Assert the outcome the user sees, plus URL or persisted state when it is part
   of the contract.
7. Exercise failure, empty, keyboard, back-navigation, and recovery cases.
8. Fake only external boundaries and rare failures; keep app routing real.
9. Fail on unexpected console and page errors; declare expected ones per test.
10. Scan rendered pages and revealed states with axe; record manual checks still
    needed.
11. Repeat timing-sensitive tests; triage flakes with traces instead of retries.
12. Record browsers, commands, results, and limits; a plan is not an execution.

## Acceptance gates

- [ ] Each journey has a visible outcome and a failure or recovery path.
- [ ] Locators are role or label based; test ids are documented contracts.
- [ ] No fixed sleeps; unexpected runtime errors fail the test.
- [ ] Suite passes with `--repeat-each=3` in parallel.
- [ ] Axe scans cover key pages and interaction states with zero violations or
      documented, owned exclusions.
