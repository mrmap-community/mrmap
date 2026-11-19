# Confirm the classification

The pull request **title** is what reaches the integration history: a merge keeps the title
and nothing else, so the change class has to be in it, and a class written only into a commit
message is thrown away at the merge.

- [ ] the title reads `<type>[(<scope>)][!]: <summary>`, with a type from
      `python3 scripts/pr_classify types` (`docs/source/development/commit-classification.rst`)
- [ ] the title carries `!` if anything here breaks an existing consumer, and the description
      says what breaks and how a caller moves — `BREAKING CHANGE:` written in a commit or in
      this description does **not** survive the merge
- [ ] a component name is a scope, not a type: `fix(mcp-setup): …`, not `mcp-setup: …`

`python3 scripts/pr_classify title "<the title>"` answers it before the check does.

# Confirm the definition of done (DoD)

- [ ] PR only contains one change (considered splitting up PR)
- [ ] unit-test added
- [ ] documentation updated
- [ ] `CHANGELOG.md` updated
