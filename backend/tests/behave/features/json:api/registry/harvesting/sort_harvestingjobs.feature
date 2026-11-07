@fixtures:test_harvesting_states.json
Feature: HarvestingJob Sort Endpoint
    As a CSW administrator,
    I want to order the harvesting runs by the progress they report about their own work,
    so that the run which is half way through its harvest answers where it belongs (#1130).

    # The progress of a run is no column of its row: #1071 annotates the steps a run took
    # and derives the percentage from them, which is what lets the endpoint offer the term.
    # The fixture answers the two shapes the order reads (the set of #1080, also behind
    # `filter_harvestingjobs.feature`): run 1080101 of catalogue Alpha ended, so it is 100,
    # and run 1080102 of the very same catalogue is working - it counted 10 records, asks
    # them with the step size 50 of a run which started without one, and has 2 files left on
    # its backlog. Its steps are 12 and two of them are done, which is 16.67 %. The 12 are the
    # 10 records, the +1 of #1071 and the 1 round trip of the 10 records asked with the step
    # size 50: the ceiling divides them as Float, since #1163, where Postgres used to divide
    # the two integer columns by truncation and answer 0. The 2 files on the backlog are that
    # one round trip of the run - its fetch call and that trip are the 2 done steps. Before
    # #1163 the round trip was in no step of its own and the scenario measured 9.09 of 11.
    # The scenarios scope on the catalogue of those two runs: the `add_harvestingjob`
    # feature runs before this one and leaves runs of its own behind, and the runs of
    # another catalogue are no answer to the order of this one.

    Background: Setup base url
        Given I use the endpoint http://localhost:8000/api/registry/harvesting/harvesting-jobs

    # Both directions of the term and the annotated value the order reads. A sort nobody
    # checks answers 200 in the order of the table, so the scenario names the run it
    # expects first together with the progress it answers with. The default order of the
    # list is the newest run first, which is the ascending answer of these two runs; the
    # descending row is the order the table cannot give (#1130).
    Scenario Outline: Can order the runs of a catalogue by their progress
        Given I set a queryparam "filter[service.id]" with value "aaaa1080-0000-4000-8000-00000000000a"
        Given I set a queryparam "sort" with value "<ordering>"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect that response json has an attribute "data.[0].id" with value "<first>"
        Then I expect that response json has an attribute "data.[0].attributes.progress" with value "<firstProgress>"
        Then I expect that response json has an attribute "data.[1].id" with value "<last>"
        Then I expect that response json has an attribute "data.[1].attributes.progress" with value "<lastProgress>"

        Examples:
            | ordering  | first   | firstProgress | last    | lastProgress |
            | progress  | 1080102 | 16.67         | 1080101 | 100.0        |
            | -progress | 1080101 | 100.0         | 1080102 | 16.67        |

    # A screen may order the runs by their progress without showing a number of it: the
    # cards of a catalogue ask one field of a run and order them by another (#1080). The
    # order reads the annotation either way, while the answer keeps showing only what the
    # client named - what a client orders by has to be annotated, what it renders is up to
    # the client (#1130).
    Scenario: Orders by a progress the answer does not show
        Given I set a queryparam "filter[service.id]" with value "aaaa1080-0000-4000-8000-00000000000a"
        Given I set a queryparam "fields[HarvestingJob]" with value "id"
        Given I set a queryparam "sort" with value "-progress"
        When I send the request with GET method
        Then I expect the response status is 200
        Then I expect that response json has an attribute "meta.pagination.count" with value "2"
        Then I expect that response json has an attribute "data.[0].id" with value "1080101"
        Then I expect that response json has an attribute "data.[1].id" with value "1080102"

    # A term which is not offered is refused rather than quietly ignored, the same refusal
    # the list answers for a filter it does not declare.
    Scenario: Can't sort by a field which is not offered
        Given I set a queryparam "sort" with value "not_a_field"
        When I send the request with GET method
        Then I expect the response status is 400
        Then I expect that response json has an attribute "errors.[0].code" with value "invalid"
