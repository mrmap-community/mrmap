# The demonstration the acceptance criteria of #1689 ask for: an intentional
# failure must end the run with a nonzero exit and leave a trace behind. It is
# never part of a CI tier — the runner excludes it by tag, and the documented
# `npm run bdd:demonstrate` command opts into it by name.
#
# It is NOT a regression scenario and asserts nothing about MrMap: the expected
# text is one the application never shows, which is the point.

@intentional-failure @negative
Feature: A red scenario reports itself red
  Proof that a failing Gherkin scenario fails the run loudly.

  Scenario: A promise the application never keeps
    Given the acceptance stack answers
    When I open the search screen
    Then I should see "this text is never rendered by the acceptance stack"
