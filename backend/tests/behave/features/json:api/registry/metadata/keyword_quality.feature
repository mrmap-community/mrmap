@no_fixtures
Feature: Keyword quality indicator of a harvested record

  A catalogue which publishes several values in one gmd:keyword element ships
  poor metadata: ten values are ten elements, not one long string (#919).
  mrmap stores exactly what the catalogue published - the merged keyword
  survives whole - and reports the finding through the quality indicator the
  explorer of #600 answers: the text on the record, the boolean in the filter.

  Scenario: A merged keyword is flagged and the api answers the flag
      Given the catalogue published a record whose keyword publishes several values
      Then the harvested record answers its insufficient quality
      And the insufficient quality filter answers the harvested record

  Scenario: A corrected re-harvest clears the flag
      Given the catalogue published a record whose keyword publishes several values
      And the catalogue corrects the record and republishes it
      Then the harvested record answers no insufficient quality
      And the insufficient quality filter answers no record

  Scenario: A legitimate keyword with one comma is no finding
      Given the catalogue published a record whose keyword carries one comma in a short phrase
      Then the harvested record answers no insufficient quality
      And the insufficient quality filter answers no record
