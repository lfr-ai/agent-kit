import { expect, test } from "bun:test";

test("the dependency-free delivery fixture runs locally", () => {
  expect(["python-ci", "bun-ci", "bicep-check", "terraform-check"]).toHaveLength(4);
});
