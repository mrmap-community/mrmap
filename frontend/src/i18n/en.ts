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
      }
    }
  }
);



export default en;