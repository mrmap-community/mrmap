# The list screens behind the menu, as one business scenario per screen family
# (#1689). The behaviour asserted is what a reviewer can see on a screenshot:
# rows appear and no error alert shows. The filter/sort matrices stay Behave's
# job (#1688 "Boundary rules").

@smoke
Feature: Record lists of the built SPA
  Every acceptance screen opens against the seeded database and shows rows.

  Scenario Outline: The <screen> screen lists the seeded records
    Given the acceptance stack answers
    When I open the <screen> screen
    Then the list answers with rows
    And no error alert appears

    Examples:
      | screen               |
      | dataset list         |
      | wms list             |
      | keyword list         |
      | language list        |
      | harvesting list      |
      | background processes |
