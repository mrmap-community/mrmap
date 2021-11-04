Feature: MapContext Rendering Layer
    As a User, 
    I want to configure the rendering behaviour of a layer, 
    So that the rendering configuration is part of the mapcontext.

  Background: Open mapcontext add page
    Given I am logged in as "mrmap" with password "mrmap"
    And the base url is "https://localhost:8000"
    And I open the site "/registry/mapcontexts/add"
    When I set "mapctx" to the inputfield "//*[@id='id_title']"
    And I set "short example of a mapcontext" to the inputfield "//*[@id='id_abstract']"
    And I click on the button "//*[@id='j1_1']//*[contains(@title, 'Add Folder')]"
    And I click on the element "//*[@id='j1_1_anchor']"
    And I click on the element "//*[@id='j1_2_anchor']"
    And I set "node1" to the inputfield "//*[@id='id_layer-1-name']"

  Scenario: Successful configure mapcontext layer tree without offerings
    And I submit the form "//body//form"
    Then I wait on element "//*[contains(text(), 'mapctx')]" for 3000ms

  Scenario: Check correct form logic for scale min max fields if scale min max is a int or float
    When I click on the element "//*[@aria-labelledby='select2-id_layer-1-rendering_layer-container']"
    And I pause for 50ms
    And I click on the element "//input[@class='select2-search__field']"
    And I set "Gemeindestrassen 1" to the inputfield "//input[@class='select2-search__field']"
    And I pause for 500ms
    And I press "Enter"
    Then I wait on element "//*[@id='id_layer-1-layer_scale_min']" for 3000ms to be enabled
    And I wait on element "//*[@id='id_layer-1-layer_scale_max']" for 3000ms to be enabled

  Scenario: Check correct form logic for scale min max fields if scale min max is not a int or float
    When I click on the element "//*[@aria-labelledby='select2-id_layer-1-rendering_layer-container']"
    And I pause for 50ms
    And I click on the element "//input[@class='select2-search__field']"
    And I set "Relative Feuchte" to the inputfield "//input[@class='select2-search__field']"
    And I pause for 500ms
    And I press "Enter"
    Then I wait on element "//*[@id='id_layer-1-layer_scale_min']" for 3000ms to not be enabled
    And I wait on element "//*[@id='id_layer-1-layer_scale_max']" for 3000ms to not be enabled

  Scenario: Check correct form logic for style selection
    When I click on the element "//*[@aria-labelledby='select2-id_layer-1-rendering_layer-container']"
    And I pause for 50ms
    And I click on the element "//input[@class='select2-search__field']"
    And I set "Gemeindestrassen 1" to the inputfield "//input[@class='select2-search__field']"
    And I pause for 500ms
    And I press "Enter"
    Then I wait on element "//*[@id='id_layer-1-layer_scale_min']" for 3000ms to not be enabled
    And I wait on element "//ul[@id='select2-id_layer-1-layer_style-results']/li[1]" for 3000ms to exist
    And I wait on element "//ul[@id='select2-id_layer-1-layer_style-results']/li[2]" for 3000ms to not exist
