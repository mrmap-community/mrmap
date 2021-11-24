import { Button } from 'antd';
import React, { FC } from 'react';
import { useNavigate } from 'react-router';

type MapContextListProps = unknown; // TODO
export const MapContextList: FC<MapContextListProps> = () => {
  const navigate = useNavigate();

  const onAddMapContextAdd = () => {
    navigate('/registry/mapcontexts/add');
  };
  return (
    <>
      <h1>MAP CONTEXT LIST</h1>
      <h2>UNDER  CONSTRUCTION</h2>
      <Button
        type='primary'
        onClick={onAddMapContextAdd}>
          Add map context
      </Button>
      </>
  );
};
