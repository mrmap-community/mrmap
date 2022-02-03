import Search from 'antd/lib/input/Search';
import React, { ReactElement } from 'react';

export const Dashboard = (): ReactElement => {
  return (
    <Search
      size='large'
      placeholder='input search text'
      allowClear={true}
    />
  );
};
