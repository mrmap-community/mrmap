import React, { ReactElement } from 'react';

import Search from 'antd/lib/input/Search';


export const Dashboard = (): ReactElement => {
  return (
    <Search
      size='large'
      placeholder='input search text'
      allowClear={true}
    />
  );
};
