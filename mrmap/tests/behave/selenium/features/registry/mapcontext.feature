Feature: MapContext Rendering Layer
    As a User, 
    I want to configure the rendering behaviour of a layer, 
    So that the rendering configuration is part of the mapcontext.

  Background: Open mapcontext add page
    Given there are set of Users in Database
      | username | password |
      | peter | password123 |
    Given I am logged in
    Given the base url is "https://localhost:8000"
    Given I open the site "/registry/mapcontexts/add"

  @skip
  Scenario: Successful configure mapcontext layer tree without offerings
    When I set "mapcontext " to the inputfield "//*[@id='id_title']"
    When I set "short example of a mapcontext" to the inputfield "//*[@id='id_abstract']"
    When I click on the button "//*[@id='j1_1']//*[contains(@title, 'Add Folder')]"
    When I click on the element "//*[@id='j1_1_anchor']"
    When I click on the element "//*[@id='j1_2_anchor']"
    When I set "node1" to the inputfield "//*[@id='id_layer-1-name']"
    When I submit the form "//body//form"
    When I pause for 500ms
   #Then I wait on element "([^"]*)?"(?: for (\d+)ms)*(?: to( not)* (be checked|be enabled|be selected|be visible|contain a text|contain a value|exist))*
    Then I expect that element "//*[text()[contains(.,'Successfully signed in.')]]" does exist

