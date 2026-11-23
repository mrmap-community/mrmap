# The list screens behind the menu, as one business scenario per screen family
# (#1689). The behaviour asserted is what a reviewer can see on a screenshot:
# rows appear, the seeded record the stack is supposed to hold is among them,
# and no error alert shows. The filter/sort matrices stay Behave's job (#1688
# "Boundary rules").
#
# `record` is the row the example can name — a value from helpers/fixtures.ts,
# never a uuid. Where a screen has no stable business identity to name (`-`),
# the scenario stops at "rows appear"; `Then the list answers with rows` only
# accepts the rows of that screen's own list, so an empty datagrid is red
# (#1689 review, finding 1).

@smoke
Feature: Record lists of the built SPA
  Every acceptance screen opens against the seeded database and shows rows.

  Scenario Outline: The <screen> screen lists the seeded records
    Given the acceptance stack answers
    When I open the <screen> screen
    Then the list answers with rows
    And the list shows the record named "<record>"
    And no error alert appears

    Examples:
      | screen               | record                     |
      | dataset list         | {seed.dataset.title}     |
      | wms list             | {seed.wms.title}         |
      | csw list             | -                        |
      | keyword list         | -                        |
      | language list        | -                        |
      | harvesting list      | -                        |
      | background processes | -                        |
