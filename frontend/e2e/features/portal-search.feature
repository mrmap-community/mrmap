# The portal search journey (#1034) as an executable business scenario, and the
# first smoke scenario of the harness (#1689). No uuid, no selector and no
# timeout appears below: the named values come from helpers/fixtures.ts and the
# waiting belongs to the step layer (#1687 invariant 2).

@smoke
Feature: Portal search over the seeded catalogue
  The portal search answers with dataset metadata and services side by side,
  and it does so without a single refused request.

  Scenario: The seeded dataset is found by its title
    Given the acceptance stack answers
    When I open the search screen
    And I search for "{seed.dataset.searchterm}"
    And I expand the results of DatasetMetadataRecord
    Then I should see "{seed.dataset.title}"
    And every API call of the scenario is answered below 400
