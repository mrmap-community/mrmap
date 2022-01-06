import { PlusCircleOutlined } from '@ant-design/icons';
import { Button, Drawer, notification } from "antd";
import React, { ReactElement, useRef, useState } from 'react';
import DatasetMetadataRepo from '../../Repos/DatasetMetadataRepo';
import RepoTable, { RepoTableColumnType } from '../Shared/Table/RepoTable';
import { buildSearchTransformText } from '../Shared/Table/TableHelper';
import './SearchDrawer.css';

const repo = new DatasetMetadataRepo();

export const SearchDrawer = (): ReactElement => {

    const [visible, setVisible] = useState<boolean>(false);

    const buttonRef = useRef<HTMLButtonElement>(null);

    const addDatasetToMap = (dataset: any) => {
      console.log(dataset);
        notification.info({
          message: `Add dataset '${dataset.title}'`
        });
    };

    const columns: RepoTableColumnType[] = [{
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
        render: (text: any, record:any) => {
          return (
            <>
                <Button
                  size='small'
                  type='primary'
                  onClick={ () => { addDatasetToMap(record); }}
                >
                  Zur Karte hinzufügen
                </Button>
            </>
          );
        }
      }, {
        dataIndex: 'search',
        title: 'Suchbegriffe',
        valueType: 'text',
        hideInTable: true,
        hideInSearch: false,
        search : {
          transform : buildSearchTransformText('search')
        }
      }
    ];

    return (
      <>
        <Button
          ref={buttonRef}
          size='large'
          className={`drawer-toggle-btn ${visible ? 'expanded' : 'collapsed'}`}
          onClick={(ev) => { setVisible(!visible); buttonRef.current?.blur(); }}
        >
          <PlusCircleOutlined />
        </Button>
        <Drawer
          className='search-drawer'
          placement='right'
          width={1000}
          visible={visible}
          closable={false}
          mask={false}
        >
          <RepoTable
            repo={repo}
            columns={columns}
            pagination={{
              defaultPageSize: 13,
              showSizeChanger: true,
              pageSizeOptions: ['10', '13', '20', '50', '100']
            }}
          />
        </Drawer>
      </>
    );
};
