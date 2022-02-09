import { Card, Image } from 'antd';
import React, { ReactElement } from 'react';

export const PageNotFound = (): ReactElement => {
  return (
    <Card title='5xx' bordered={false} >
      <Image
        alt={'Ill Mr. Map logo'}
        src={process.env.PUBLIC_URL + '/mr_map_500.png'}
      />
    </Card>
  );
};
