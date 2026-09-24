import englishMessages from 'ra-language-english';

import lodashMerge from 'lodash/merge';

const en = lodashMerge(
  englishMessages,
  {
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
      },
      WebMapServiceUpdateJob: {
        reviewRequired: "Review is required",
        reviewRequiredSubheader: "Remote capabilities contain changes that are not applied yet.",
        lastUpdateJobs: "Last Updatejobs",
        lastUpdateJobsSubheader: "No action is needed."
      }
    }
  }
);



export default en;