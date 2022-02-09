import { Card, Image } from 'antd';
import React, { ReactElement } from 'react';

export const PageNotFound = (): ReactElement => {
  return (
    <Card title='404 - Page Not Found' bordered={false} >
      <Image
        alt={'Confused Mr. Map logo'}
        src={process.env.PUBLIC_URL + '/mr_map_404.png'}
      />
    </Card>
  );
};
