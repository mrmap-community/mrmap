Feature: MapContext Layer Selection options
  As a User,
  I want to configure the selection behaviour of a layer,
  so that the selection configuration is part of the mapcontext.

  Background: User is logged in
    Given the base url is "https://localhost:8000"
    Given I am logged in

  Scenario: Selecting a Dataset populates the selection dropdown with the queryable layers associated with the Dataset.
    Given I open the site "/registry/mapcontexts/add/"
    When I click on the element "//select[@id='id_layer-0-dataset_metadata']/following-sibling::span"
    When I click on the element "//input[@class='select2-search__field']"
    When I set "Relative Feuchte" to the inputfield "//input[@class='select2-search__field']"
    When I press "Enter"
    When I click on the element "//select[@id='id_layer-0-selection_layer']/following-sibling::span"
    Then I expect that element "//ul[@id='select2-id_layer-0-selection_layer-results']/li[1]" does exist
    Then I expect that element "//ul[@id='select2-id_layer-0-selection_layer-results']/li[2]" does not exist
    Then I expect that element "//ul[@id='select2-id_layer-0-selection_layer-results']" contains the text "Relative Feuchte an RBSN Stationen (feb6f9fa-db2b-4738-86d9-ce2638dba74d)"
