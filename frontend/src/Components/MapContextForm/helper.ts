import { ReactNode } from 'react';
import { RepoTableColumnType } from '../Shared/Table/RepoTable';
import { buildSearchTransformText } from '../Shared/Table/TableHelper';

export const getDatasetMetadataColumns = 
  (renderActions: (text: any, record:any) => ReactNode): RepoTableColumnType[] => [{
    dataIndex: 'title',
    title: 'Titel',
    // disable rendering by return null in renderFormItem, because we cannot set 'hideInSearch: true' for
    // every data column (otherwise our custom search field would not be rendered by the antd Pro Table)
    renderFormItem: () => {
      return null;
    }
    // hideInSearch: true
    }, {
      dataIndex: 'abstract',
      title: 'Zusammenfassung',
      hideInSearch: true
    }, {
      dataIndex: 'id',
      hideInTable: true
    }, {
      dataIndex: 'xml_backup_file',
      hideInTable: true
    }, {
      dataIndex: 'access_constraints',
      hideInTable: true
    }, {
      dataIndex: 'fees',
      hideInTable: true
    }, {
      dataIndex: 'use_limitation',
      hideInTable: true
    }, {
      dataIndex: 'file_identifier',
      hideInTable: true
    }, {
      dataIndex: 'license_source_note',
      hideInTable: true
    }, {
      dataIndex: 'date_stamp',
      hideInTable: true
    }, {
      dataIndex: 'origin',
      hideInTable: true
    }, {
      dataIndex: 'origin_url',
      hideInTable: true
    }, {
      dataIndex: 'is_broken',
      hideInTable: true
    }, {
      dataIndex: 'is_customized',
      hideInTable: true
    }, {
      dataIndex: 'insufficient_quality',
      hideInTable: true
    }, {
      dataIndex: 'is_searchable',
      hideInTable: true
    }, {
      dataIndex: 'hits',
      hideInTable: true
    }, {
      dataIndex: 'spatial_res_type',
      hideInTable: true
    }, {
      dataIndex: 'spatial_res_value',
      hideInTable: true
    }, {
      dataIndex: 'format',
      hideInTable: true
    }, {
      dataIndex: 'charset',
      hideInTable: true
    }, {
      dataIndex: 'inspire_top_consistence',
      hideInTable: true
    }, {
      dataIndex: 'preview_image',
      hideInTable: true
    }, {
      dataIndex: 'lineage_statement',
      hideInTable: true
    }, {
      dataIndex: 'update_frequency_code',
      hideInTable: true
    }, {
      dataIndex: 'bounding_geometry',
      hideInTable: true
    }, {
      dataIndex: 'dataset_id',
      hideInTable: true
    }, {
      dataIndex: 'dataset_id_code_space',
      hideInTable: true
    }, {
      dataIndex: 'inspire_interoperability',
      hideInTable: true
    }, {
      key: 'actions',
      title: 'Aktionen',
      valueType: 'option',
      render: renderActions
    }, {
      dataIndex: 'search',
      title: 'Suchbegriffe',
      valueType: 'text',
      hideInTable: true,
      hideInSearch: false,
      search : {
        transform : buildSearchTransformText('search')
      }
    },
    {
      dataIndex: 'is_accessible',
      hideInTable: true
    }
];
