import { UnorderedListOutlined } from '@ant-design/icons';
import { List, Progress } from 'antd';
import Paragraph from 'antd/lib/typography/Paragraph';
import Title from 'antd/lib/typography/Title';
import React, { useEffect } from 'react';
import { useOperationMethod } from 'react-openapi-client';
import { useDispatch, useSelector } from 'react-redux';
import { backgroundProcessesSelectors } from '../../Services/ReduxStore/Reducers/BackgroundProcess';

export const BackgroundProcessList = (): JSX.Element => {
  const backgroundProcesses = useSelector(backgroundProcessesSelectors.selectAll);
  const [
    listBackgroundProcess, 
    { loading: listBackgroundProcessLoading, response: listBackgroundProcessResponse }
  ] = useOperationMethod('listBackgroundProcess');

  const dispatch = useDispatch();
  
  useEffect(() => {
    if (listBackgroundProcessResponse){
      dispatch(
        {
          type: 'backgroundProcesses/set',
          payload: listBackgroundProcessResponse.data.data
        }
      );
    } else if (!listBackgroundProcessLoading) {
      listBackgroundProcess([{ name: 'page[size]', value: '5', in: 'query' }]);
    }
  }, [dispatch, listBackgroundProcess, listBackgroundProcessLoading, listBackgroundProcessResponse]);


  const getStatus = (backgroundProcess: any): any => {
    switch (backgroundProcess.attributes.status) {
    case 'running':
      return 'active';
    case 'successed':
      return 'success';
    case 'failed':
      return 'exception';
    case 'unknown':
    case 'pending':
    default:
      return 'normal';
    }
  };

  return (
    <List
      size={'small'}
      header={<Title level={5}><UnorderedListOutlined /> Background Processes</Title>}
      loading={listBackgroundProcessLoading}
      dataSource={backgroundProcesses}
      renderItem={backgroundProcess => (
        <List.Item 
          key={backgroundProcess.id}
        >
          <List.Item.Meta
            title={
              <Paragraph 
                ellipsis={true}
              >
                {backgroundProcess.attributes.description}
              </Paragraph>
            }
            description={
              <Progress
                percent={Math.round(backgroundProcess.attributes.progress)}
                status={getStatus(backgroundProcess)} 
              />
            }
            
          />
          
        </List.Item>
      )}
    />
  );
};


