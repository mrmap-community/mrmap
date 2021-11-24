import Search from 'antd/lib/input/Search';
import React, { ReactElement } from 'react';

export const Dashboard = (): ReactElement => {
  const onSearch = (value:string) => {
    /* eslint-disable-next-line */
    console.log(value);
  };

  return (
    <Search
      size='large'
      placeholder='input search text'
      allowClear={true}
      onSearch={onSearch}
    />
  );
};
