Feature: user login
  As a User,
  I want to login 
  So that I can use the MrMap UI.

  Background: setup users and open browser
    Given there are set of Users in Database
      | username | password |
      | peter | password123 | 
    Given the base url is "https://localhost:8000"
    Given I open the site "/"

  Scenario: Successful user login process 
    When I set "peter" to the inputfield "//*[@id='id_username']"
    When I set "password123" to the inputfield "//*[@id='id_password']"
    When I click on the button "//button[@type='submit']"
    Then I expect that element "//*[text()[contains(.,'Successfully signed in.')]]" does exist
    
  Scenario: Failed user login process with wrong password
    When I set "peter" to the inputfield "//*[@id='id_username']"
    When I set "password1234" to the inputfield "//*[@id='id_password']"
    When I click on the button "//button[@type='submit']"
    Then I expect that element "//*[text()[contains(.,'Please enter a correct username and password. Note that both fields may be case-sensitive.')]]" does exist
  
  Scenario: Failed user login process with wrong username
    When I set "peter123" to the inputfield "//*[@id='id_username']"
    When I set "password123" to the inputfield "//*[@id='id_password']"
    When I click on the button "//button[@type='submit']"
    Then I expect that element "//*[text()[contains(.,'Please enter a correct username and password. Note that both fields may be case-sensitive.')]]" does exist
    