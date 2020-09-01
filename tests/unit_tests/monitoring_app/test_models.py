"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 31.08.20

"""
from datetime import timedelta, datetime
import datetime
from django.test import TestCase

from monitoring.enums import HealthStateEnum
from monitoring.models import HealthState
from monitoring.settings import WARNING_RESPONSE_TIME, CRITICAL_RESPONSE_TIME
from tests.baker_recipes.db_setup import create_superadminuser, create_wms_service, create_monitoring_result, \
    create_monitoring_run
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD


class ServiceFiltersTestCase(TestCase):
    def setUp(self):
        self.user_password = PASSWORD
        self.user = create_superadminuser()
        self.wms_services = create_wms_service(group=self.user.get_groups().first(), how_much_services=1)
        self.monitoring_run = create_monitoring_run()[0]

    def test_run_health_state(self):
        """ Tests the run_health_state function and the subordinated private calculating functions

        Returns:

        """
        create_monitoring_result(monitoring_run=self.monitoring_run,
                                 metadata=self.wms_services[0],
                                 how_much_results=10)

        health_state = HealthState(monitoring_run=self.monitoring_run,
                                   metadata=self.wms_services[0])
        health_state.run_health_state()

        self.assertEqual(health_state.health_state_code, HealthStateEnum.OK.value, msg="The health state is not ok")
        self.assertEqual(health_state.average_response_time_1w, timedelta(milliseconds=WARNING_RESPONSE_TIME-1))
        self.assertEqual(health_state.average_response_time_1m, timedelta(milliseconds=WARNING_RESPONSE_TIME-1))
        self.assertEqual(health_state.average_response_time_3m, timedelta(milliseconds=WARNING_RESPONSE_TIME-1))
        self.assertEqual(health_state.reliability_1w, 100)
        self.assertEqual(health_state.reliability_1m, 100)
        self.assertEqual(health_state.reliability_3m, 100)

    def test_run_health_state_response_code_401(self):
        """ Tests the run_health_state function and the subordinated private calculating functions

        Returns:

        """
        create_monitoring_result(monitoring_run=self.monitoring_run,
                                 metadata=self.wms_services[0],
                                 status_code=401)

        health_state = HealthState(monitoring_run=self.monitoring_run,
                                   metadata=self.wms_services[0])
        health_state.run_health_state()

        self.assertEqual(health_state.health_state_code, HealthStateEnum.OK.value, msg="The health state is not ok")
        self.assertEqual(health_state.average_response_time_1w, timedelta(milliseconds=WARNING_RESPONSE_TIME-1))
        self.assertEqual(health_state.average_response_time_1m, timedelta(milliseconds=WARNING_RESPONSE_TIME-1))
        self.assertEqual(health_state.average_response_time_3m, timedelta(milliseconds=WARNING_RESPONSE_TIME-1))
        self.assertEqual(health_state.reliability_1w, 100)
        self.assertEqual(health_state.reliability_1m, 100)
        self.assertEqual(health_state.reliability_3m, 100)

    def test_run_health_state_with_critical_results(self):
        """ Tests the run_health_state function and the subordinated private calculating functions

        Returns:

        """
        # create two HealthStateEnum.OK results
        create_monitoring_result(monitoring_run=self.monitoring_run,
                                 metadata=self.wms_services[0],
                                 duration=timedelta(milliseconds=100),
                                 how_much_results=2,)
        # create two HealthStateEnum.CRITICAL results
        create_monitoring_result(monitoring_run=self.monitoring_run,
                                 metadata=self.wms_services[0],
                                 status_code=404,
                                 available=False,
                                 duration=timedelta(milliseconds=100),
                                 how_much_results=1, )
        create_monitoring_result(monitoring_run=self.monitoring_run,
                                 metadata=self.wms_services[0],
                                 status_code=200,
                                 available=True,
                                 duration=timedelta(seconds=10, ),
                                 how_much_results=1, )

        # we've got 3 monitoring results that are available and 1 that is not available
        # we've got 1 monitoring result with critical response time 10 s + CRITICAL_RESPONSE_TIME
        # The Health state must be critical and the average response time must be (3 * 100 ms + 10 s) / 4 = 2575
        # The reliability statistic must be 0 %

        health_state = HealthState(monitoring_run=self.monitoring_run,
                                   metadata=self.wms_services[0])
        health_state.run_health_state()

        self.assertEqual(health_state.health_state_code, HealthStateEnum.CRITICAL.value, msg="The health state is not critical")
        self.assertEqual(health_state.average_response_time_1w.total_seconds()*1000, 2575)
        self.assertEqual(health_state.average_response_time_1m.total_seconds()*1000, 2575)
        self.assertEqual(health_state.average_response_time_3m.total_seconds()*1000, 2575)
        self.assertEqual(health_state.reliability_1w, 0)
        self.assertEqual(health_state.reliability_1m, 0)
        self.assertEqual(health_state.reliability_3m, 0)

    def test_calculate_reliability(self):
        """ Tests the run_health_state function and the subordinated private calculating functions

        Returns:

        """
        # first we need some monitoring runs to get meaningful testdata
        monitoring_runs = create_monitoring_run(how_much_runs=3)

        # create two HealthStateEnum.OK results for the first monitoring run
        create_monitoring_result(monitoring_run=monitoring_runs[0],
                                 metadata=self.wms_services[0],
                                 duration=timedelta(milliseconds=100),
                                 how_much_results=2,)

        # run_health_state for the first monitoring run ==> HealthStateEnum.OK.value
        health_state = HealthState(monitoring_run=monitoring_runs[0],
                                   metadata=self.wms_services[0])
        health_state.run_health_state()

        # create two HealthStateEnum.CRITICAL results for the second monitoring run
        create_monitoring_result(monitoring_run=monitoring_runs[1],
                                 metadata=self.wms_services[0],
                                 available=False,
                                 status_code=404,
                                 duration=timedelta(milliseconds=200),
                                 how_much_results=2, )

        # run_health_state for the 2. monitoring run ==> HealthStateEnum.CRITICAL.value
        health_state = HealthState(monitoring_run=monitoring_runs[1],
                                   metadata=self.wms_services[0])
        health_state.run_health_state()

        # create one HealthStateEnum.CRITICAL results for the 3. monitoring run ==> this will be a critical one cause of 1 hour duration
        create_monitoring_result(monitoring_run=monitoring_runs[2],
                                 metadata=self.wms_services[0],
                                 status_code=200,
                                 duration=timedelta(minutes=1),
                                 how_much_results=1, )

        # run_health_state for the 3. monitoring run ==> HealthStateEnum.CRITICAL.value
        health_state = HealthState(monitoring_run=monitoring_runs[2],
                                   metadata=self.wms_services[0])
        health_state.run_health_state()

        # reliability: 1st HealthState is OK - 2nd HS is CRITICAL - 3th HS is CRITICAL ==> reliability is only  1 / 3 %
        # average_response_time: (100 ms + 200 ms + 60000 ms) / 3 = 20100 ms

        self.assertEqual(health_state.health_state_code, HealthStateEnum.CRITICAL.value, msg="The health state is not critical")
        self.assertEqual(health_state.average_response_time_1w.total_seconds()*1000, 20100.0)
        self.assertEqual(health_state.average_response_time_1m.total_seconds()*1000, 20100.0)
        self.assertEqual(health_state.average_response_time_3m.total_seconds()*1000, 20100.0)
        self.assertEqual(round(health_state.reliability_1w, 2), round(1/3*100, 2))
        self.assertEqual(round(health_state.reliability_1m, 2), round(1/3*100, 2))
        self.assertEqual(round(health_state.reliability_3m, 2), round(1/3*100, 2))

    def test_3m_statistics(self):
        today = datetime.date.today()
        three_mon_timedelta = datetime.timedelta(days=(3 * 365 / 12) - 1)
        one_mon_timedelta = datetime.timedelta(days=(1 * 365 / 12) - 1)
        one_week_timedelta = datetime.timedelta(days=6)

        three_mon_ago = today - three_mon_timedelta
        one_mon_ago = today - one_mon_timedelta
        one_week_ago = today - one_week_timedelta

        # create three monitoring runs with different datetimes
        monitoring_run_three_mon_ago = create_monitoring_run(end=three_mon_ago, how_much_runs=2)
        monitoring_run_one_mon_ago = create_monitoring_run(end=one_mon_ago, how_much_runs=2)
        monitoring_run_one_week_ago = create_monitoring_run(end=one_week_ago, how_much_runs=2)

        # create three monitoring runs with different timestamps
        create_monitoring_result(monitoring_run=monitoring_run_three_mon_ago[0],
                                 metadata=self.wms_services[0],
                                 duration=timedelta(milliseconds=100),
                                 timestamp=three_mon_ago,
                                 how_much_results=2,)
        # run_health_state for the first monitoring run ==> HealthStateEnum.OK.value
        health_state_3m_1 = HealthState(monitoring_run=monitoring_run_three_mon_ago[0],
                                        metadata=self.wms_services[0])
        health_state_3m_1.run_health_state()

        create_monitoring_result(monitoring_run=monitoring_run_three_mon_ago[1],
                                 metadata=self.wms_services[0],
                                 duration=timedelta(milliseconds=200),
                                 timestamp=three_mon_ago,
                                 how_much_results=2, )
        health_state_3m_2 = HealthState(monitoring_run=monitoring_run_three_mon_ago[1],
                                        metadata=self.wms_services[0])
        health_state_3m_2.run_health_state()

        create_monitoring_result(monitoring_run=monitoring_run_one_mon_ago[0],
                                 metadata=self.wms_services[0],
                                 duration=timedelta(milliseconds=100),
                                 timestamp=one_mon_ago,
                                 how_much_results=2, )
        health_state_1m_1 = HealthState(monitoring_run=monitoring_run_one_mon_ago[0],
                                        metadata=self.wms_services[0])
        health_state_1m_1.run_health_state()

        create_monitoring_result(monitoring_run=monitoring_run_one_mon_ago[1],
                                 metadata=self.wms_services[0],
                                 duration=timedelta(milliseconds=200),
                                 timestamp=three_mon_ago,
                                 how_much_results=2, )

        health_state_1m_2 = HealthState(monitoring_run=monitoring_run_one_mon_ago[1],
                                        metadata=self.wms_services[0])
        health_state_1m_2.run_health_state()

        create_monitoring_result(monitoring_run=monitoring_run_one_week_ago[0],
                                 metadata=self.wms_services[0],
                                 duration=timedelta(minutes=1),
                                 timestamp=one_week_ago,
                                 how_much_results=2, )
        health_state_1w_1 = HealthState(monitoring_run=monitoring_run_one_week_ago[0],
                                        metadata=self.wms_services[0])
        health_state_1w_1.run_health_state()
        create_monitoring_result(monitoring_run=monitoring_run_one_week_ago[1],
                                 metadata=self.wms_services[0],
                                 duration=timedelta(milliseconds=200),
                                 timestamp=three_mon_ago,
                                 how_much_results=2, )

        health_state_1w_2 = HealthState(monitoring_run=monitoring_run_one_week_ago[1],
                                        metadata=self.wms_services[0])
        health_state_1w_2.run_health_state()

        # health_state_1w is critical:
        # reliability: reliability_3m is 4 / 6 % | reliability_1m is 2 / 4 % | reliability_1w is 0 / 2 %
        # average_response_time_3m is ( 150 + 150 + 30100 ) / 3 ms
        # average_response_time_1m ( 150 + 30100 ) / 2 ms
        # average_response_time_1w 30100 ms

        self.assertEqual(health_state_1w_2.health_state_code, HealthStateEnum.CRITICAL.value, msg="The health state is not critical")
        self.assertEqual(round(health_state_1w_2.average_response_time_3m.total_seconds()*1000, 2), round((100 + 200 + 100 + 200 + 60000 + 200) / 6, 2))
        self.assertEqual(round(health_state_1w_2.average_response_time_1m.total_seconds()*1000, 2), round((60000 + 200 + 100 + 200) / 4, 2))
        self.assertEqual(round(health_state_1w_2.average_response_time_1w.total_seconds()*1000, 2), round((60000 + 200) / 2, 2))

        self.assertEqual(round(health_state_1w_2.reliability_3m, 2), round(4/6*100, 2))
        self.assertEqual(round(health_state_1w_2.reliability_1m, 2), round(2/4*100, 2))
        self.assertEqual(round(health_state_1w_2.reliability_1w, 2), round(0/2*100, 2))
