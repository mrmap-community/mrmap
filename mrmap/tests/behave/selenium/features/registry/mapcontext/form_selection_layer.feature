Feature: MapContext Layer Selection options
  As a User,
  I want to configure the selection behaviour of a layer,
  so that the selection configuration is part of the mapcontext.

  Background: User is logged in
    Given the base url is "https://localhost:8000"
    Given I am logged in as "mrmap" with password "mrmap"

  Scenario: Selecting a Dataset populates the selection dropdown with the queryable layers associated with the Dataset.
    Given I open the site "/registry/mapcontexts/add/"
    When I click on the element "//select[@id='id_layer-0-dataset_metadata']/following-sibling::span"
    When I click on the element "//input[@class='select2-search__field']"
    When I set "2m Temperatur" to the inputfield "//input[@class='select2-search__field']"
    When I pause for 500ms
    When I press "Enter"
    When I click on the element "//select[@id='id_layer-0-selection_layer']/following-sibling::span"
    Then I expect that element "//ul[@id='select2-id_layer-0-selection_layer-results']/li[1]" does exist
    Then I expect that element "//ul[@id='select2-id_layer-0-selection_layer-results']/li[2]" does not exist
    Then I expect that element "//ul[@id='select2-id_layer-0-selection_layer-results']" contains the text "2m Temperatur an RBSN Stationen (6e15cee7-1280-47df-804c-d4c728441b77)"

  Scenario: Configuring the selection layer and submitting the form stores a MapContext with selection layer.
    Given I open the site "/registry/mapcontexts/add/"
    When I set "Test Selection MapContext" to the inputfield "//*[@id='id_title']"
    When I set "MapContext with selection WMS layer" to the inputfield "//*[@id='id_abstract']"
    When I click on the element "//select[@id='id_layer-0-selection_layer']/following-sibling::span"
    When I click on the element "//input[@class='select2-search__field']"
    When I set "Relative Feuchte" to the inputfield "//input[@class='select2-search__field']"
    When I pause for 500ms
    When I press "Enter"
    When I submit the form "//body//form"
    When I pause for 1000ms
    Then I expect the url to contain "/registry/mapcontexts"
      And I expect the url to not contain "/registry/mapcontexts/add"
      And I expect a MapContextLayer in the DB that uses WMS Layer "Relative Feuchte an RBSN Stationen" for selection and belongs to MapContext "Test Selection MapContext"