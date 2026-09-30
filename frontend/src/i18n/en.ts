import englishMessages from 'ra-language-english';

import lodashMerge from 'lodash/merge';

const en = lodashMerge(
  englishMessages,
  {
    systemInfo: {
      "title": "System information",
      "unavailable": "System information is unavailable.",
      "mrmapRelease": "MrMap release",
      "djangoVersion": "Django version",
      "pythonVersion": "Python version",
      "postgresqlVersion": "PostgreSQL version",
      "databaseName": "Database name",
      "databaseSize": "Database size",
      "celeryWorkerCount": "Celery worker count",
      "redisUp": "Redis reachable",
      "systemTime": "System time"
    },
    systemStatus: {
      "title": "System status",
      "observed": "Observed at",
      "stale": "Monitoring data is stale or unavailable. Current health is unknown.",
      "workers": "Celery workers",
      "beat": "Celery Beat",
      "redis": "Redis",
      "database": "PostgreSQL",
      "noObservation": "No current observation",
      "lastSeen": "Last heartbeat",
      "unavailable": "System monitoring is unavailable.",
      "states": {
        "healthy": "Healthy",
        "down": "Down",
        "unknown": "Unknown",
        "degraded": "Degraded"
      }
    },
    ra: {
      action: {
        active: 'Click to activate %{name}',
        deactive: 'Click to deactivate %{name}',
        show_all: 'Show all %{name}',      
        add: 'Add %{name}',
        mapviewer: 'Mapviewer'
      },
      list: {
        actions: "Actions"
      },
      notification: {
        updated_with_errors: "Element updated, but some related items could not be saved |||| %{smart_count} elements updated, but some related items could not be saved",
        created_with_errors: "Element created, but some related items could not be saved |||| %{smart_count} elements created, but some related items could not be saved",
      },
    },
    resources: {
      ChangeLog: {
        historyDate: "Datestamp",
        historyUser: "User",
        historyType: "Action",
        historyRelation: "Object",
        lastChanges: "Last Changes",
        created: "create",
        deleted: "deleted",
        updated: "updated"
      },
      WebMapServiceMonitoringRun: {
        lastMonitoringRuns: "Last monitoring runs",
        passed: "Passed",
        failed: "Failed",
        noSetting: "Monitoring is not configured for this WMS.",
        createSetting: "Create monitoring setting",
        settingsDisabled: "Monitoring is disabled. Enable a monitoring setting to schedule runs.",
        waitingForFirstRun: "No monitoring runs yet. Waiting for the first scheduled run.",
        runOverdue: "A scheduled monitoring run is overdue. Check the monitoring scheduler.",
        settingsLoadError: "Unable to load monitoring settings."
      },
      WebMapServiceUpdateJob: {
        reviewRequired: "Review is required",
        reviewRequiredSubheader: "Remote capabilities contain changes that are not applied yet.",
        lastUpdateJobs: "Last Updatejobs",
        lastUpdateJobsSubheader: "No action is needed.",
        noSetting: "Automatic updates are not configured for this WMS.",
        createSetting: "Create update setting",
        settingsDisabled: "Automatic updates are disabled. Enable an update setting to schedule jobs.",
        waitingForFirstRun: "No update jobs yet. Waiting for the first scheduled run.",
        runOverdue: "A scheduled update job is overdue. Check the update scheduler.",
        settingsLoadError: "Unable to load update settings."
      }
    }
  }
);



export default en;