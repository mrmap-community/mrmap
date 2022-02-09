import React, { ReactElement } from 'react';

import { Card, Image } from 'antd';


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
