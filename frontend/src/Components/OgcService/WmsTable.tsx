import React from 'react';

import WmsRepo from '../../Repos/WmsRepo';
import RepoTable from '../Shared/Table/RepoTable';

const repo = new WmsRepo();

const columns:any = [{
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
  title: 'Erstellt',
  fieldProps: {
    // format: moment.localeData().longDateFormat('L')
    format: 'DD.MM.YYYY HH:mm:ss'
  }
}, {
  dataIndex: 'last_modified_at',
  title: 'Zuletzt modifiziert',
  fieldProps: {
    // format: moment.localeData().longDateFormat('L')
    format: 'DD.MM.YYYY HH:mm:ss'
  }
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
}];

export const WmsTable = (): JSX.Element => {
  return <RepoTable repo={repo} columnHints={columns} addRecord='/registry/services/add'/>;
};

export default WmsTable;
