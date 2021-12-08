import { ProColumnType } from '@ant-design/pro-table';
import { Button } from 'antd';
import React, { useRef } from 'react';

import WmsRepo from '../../Repos/WmsRepo';
import RepoTable, { RepoActionType } from '../Shared/Table/RepoTable';

const repo = new WmsRepo();

export const WmsTable = (): JSX.Element => {
  const actionRef = useRef<RepoActionType>();
  const columns: ProColumnType[] = [{
    dataIndex: 'id',
    title: 'ID',
    ellipsis: true
  }, {
    dataIndex: 'title',
    title: 'Titel'
  }, {
    dataIndex: 'abstract',
    title: 'Zusammenfassung'
  }, {
    dataIndex: 'created_at',
    title: 'Erstellt'
  }, {
    dataIndex: 'last_modified_at',
    title: 'Zuletzt modifiziert'
  }, {
    dataIndex: 'version',
    title: 'Version'
  }, {
    dataIndex: 'service_url',
    title: 'Service URL'
  }, {
    dataIndex: 'get_capabilities_url',
    title: 'Capabilities URL'
  }, {
    dataIndex: 'xml_backup_file',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'file_identifier',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'access_constraints',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'fees',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'use_limitation',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'license_source_note',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'date_stamp',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'origin',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'origin_url',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'is_broken',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'is_customized',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'insufficient_quality',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'is_searchable',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'hits',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'is_active',
    hideInTable: true,
    hideInSearch: true
  }, {
    key: 'actions',
    title: 'Actions',
    valueType: 'option',
    render: (text: any, record:any) => {
      return (
        <>
            <Button
              danger
              size='small'
              onClick={ () => {
                actionRef.current?.deleteRecord(record);
              }}
            >
              Delete
            </Button>
        </>
      );
    }
  }];

  return <RepoTable
            repo={repo}
            columns={columns}
            actionRef={actionRef as any}
            addRecord='/registry/services/add'
          />;
};

export default WmsTable;
