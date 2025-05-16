import englishMessages from 'ra-language-english';

import lodashMerge from 'lodash/merge';

const en = lodashMerge(
  englishMessages,
  {
    ra: {
      action: {
        show_all: 'Show all %{name}'
      }
    }
  }
);



export default en;