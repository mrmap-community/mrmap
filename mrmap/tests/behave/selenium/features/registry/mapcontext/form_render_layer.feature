Feature: MapContext Rendering Layer
    As a User, 
    I want to configure the rendering behaviour of a layer, 
    So that the rendering configuration is part of the mapcontext.

  Background: Open mapcontext add page
    Given I am logged in as "mrmap" with password "mrmap"
    And the base url is "https://localhost:8000"
    And I open the site "/registry/mapcontexts/add"

  Scenario: Successful configure mapcontext layer tree without offerings
    When I set "mapctx" to the inputfield "//*[@id='id_title']"
    And I set "short example of a mapcontext" to the inputfield "//*[@id='id_abstract']"
    And I click on the button "//*[@id='j1_1']//*[contains(@title, 'Add Folder')]"
    And I click on the element "//*[@id='j1_1_anchor']"
    And I click on the element "//*[@id='j1_2_anchor']"
    And I set "node1" to the inputfield "//*[@id='id_layer-1-name']"
    And I submit the form "//body//form"
    Then I wait on element "//*[contains(text(), 'mapctx')]" for 1000ms

