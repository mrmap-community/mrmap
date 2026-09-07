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
        add: 'Add %{name}'
      },
      list: {
        actions: "Actions"
      }
    },
    resources: {
      ChangeLog: {
        historyDate: "Datestamp",
        historyUser: "User",
        historyType: "Action",
        historyRelation: "Object",
        lastChanges: "Last Changes",
      }
    }
  }
);



export default en;