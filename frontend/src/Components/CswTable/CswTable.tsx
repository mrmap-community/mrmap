import { Button, Space } from 'antd';
import React, { useRef } from 'react';
import RepoTable, { RepoActionType, RepoTableColumnType } from '../Shared/RepoTable/NewRepoTable';
import { buildSearchTransformDateRange } from '../Shared/RepoTable/TableHelper';



const CswTable = (): JSX.Element => {
  const actionRef = useRef<RepoActionType>();
  const columns: RepoTableColumnType[] = [{
    dataIndex: 'id',
    title: 'ID'
  }, {
    dataIndex: 'title',
    title: 'Titel'
  }, {
    dataIndex: 'abstract',
    title: 'Zusammenfassung'
  }, {
    dataIndex: 'createdAt',
    title: 'Erstellt',
    hideInSearch: true
  }, {
    dataIndex: 'createdBetween',
    title: 'Erstellt',
    valueType: 'dateRange',
    fieldProps: {
      format: 'DD.MM.YYYY',
      allowEmpty: [true, true]
    },
    search: {
      transform: buildSearchTransformDateRange('createdAt')
    },
    hideInTable: true
  }, {
    dataIndex: 'lastModifiedAt',
    title: 'Modifiziert',
    hideInSearch: true
  }, {
    dataIndex: 'lastModifiedBetween',
    title: 'Modifiziert',
    valueType: 'dateRange',
    fieldProps: {
      format: 'DD.MM.YYYY',
      allowEmpty: [true, true]
    },
    search: {
      transform: buildSearchTransformDateRange('lastModifiedAt')
    },
    hideInTable: true
  }, {
    dataIndex: 'version',
    title: 'Version'
  }, {
    dataIndex: 'serviceUrl',
    title: 'Service URL'
  }, {
    dataIndex: 'getCapabilitiesUrl',
    title: 'Capabilities URL'
  }, {
    dataIndex: 'xmlBackupFile',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'fileIdentifier',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'accessConstraints',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'fees',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'useLimitation',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'licenseSourceNote',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'dateStamp',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'origin',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'originUrl',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'isBroken',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'isCustomized',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'insufficientQuality',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'isSearchable',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'hits',
    hideInTable: true,
    hideInSearch: true
  }, {
    dataIndex: 'isActive',
    hideInTable: true,
    hideInSearch: true
  }, {
    key: 'actions',
    title: 'Aktionen',
    valueType: 'option',
    render: (text: any, record:any) => {
      return (
        <>
          <Space size='middle'>
            <Button
              danger
              size='small'
              onClick={ () => {
                actionRef.current?.deleteRecord(record);
              }}
            >
              Löschen
            </Button>
          </Space>
        </>
      );
    }
  }];

  return <RepoTable
    resourceType='CatalougeService'
    columns={columns}
    actionRef={actionRef as any}
    onAddRecord='/registry/services/csw/add'
  />;
};

export default CswTable;
