import Search from 'antd/lib/input/Search';
import React from 'react';

export const Dashboard = () => {
  const onSearch = (value:string) => console.log(value);

  return (
    <Search
      size='large'
      placeholder='input search text'
      allowClear={true}
      onSearch={onSearch}
    />
  );
};
