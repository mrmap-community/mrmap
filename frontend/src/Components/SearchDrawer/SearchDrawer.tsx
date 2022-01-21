import { PlusCircleOutlined } from '@ant-design/icons';
import { Button, Drawer, Tooltip } from "antd";
import React, { cloneElement, ReactElement, useEffect, useRef, useState } from 'react';
import DatasetMetadataRepo from '../../Repos/DatasetMetadataRepo';
import RepoTable, { RepoTableColumnType } from '../Shared/Table/RepoTable';
import { buildSearchTransformText } from '../Shared/Table/TableHelper';
import './SearchDrawer.css';

export interface CustomContentType {
  title: string; 
  icon: ReactElement, 
  isVisible: boolean; 
  content: ReactElement, 
  onTabCickAction: () => void;
}

const repo = new DatasetMetadataRepo();

export const SearchDrawer = ({
  addDatasetToMapAction = () => undefined,
  customContent=[],
  isOpenByDefault=false
}:{
  addDatasetToMapAction?: (dataset: any) => void;
  customContent?: CustomContentType[] | never[];
  isOpenByDefault?: boolean
}): ReactElement => {

    const [activeTab,setActiveTab] = useState<string>('');
    const [isDrawerVisible, setIsDrawerVisible] = useState<boolean>(isOpenByDefault);
    const buttonRef = useRef<HTMLButtonElement>(null);
    
    useEffect(() => {
      if(!isDrawerVisible) {
        setActiveTab('');
      }
    }, [isDrawerVisible]);

    const onAddDatasetToMap = (dataset: any) => {
      addDatasetToMapAction(dataset); 
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
                  disabled={record.layers.length === 0 || !record.layers}
                  size='small'
                  type='primary'
                  onClick={ () => { onAddDatasetToMap(record); }}
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
      },
      {
        dataIndex: 'is_accessible',
        hideInTable: true
      }
    ];

    return (
      <>
        <div className={`drawer-toggle-tabs ${isDrawerVisible ? 'expanded' : 'collapsed'}`}>
          {customContent.length > 0 && (
            customContent.map((content:CustomContentType, index: number) => (
              <Tooltip 
                title={content.title}
                placement='left'
                key={index}
              >
                <Button
                  ref={buttonRef}
                  size='large'
                  className={`drawer-toggle-btn ${activeTab === String(index) && 'drawer-toggle-btn--active'}`}
                  onClick={(ev) => { 
                    content.onTabCickAction();
                    if(activeTab === String(index)) setIsDrawerVisible(false);
                    if(!isDrawerVisible && !activeTab) setIsDrawerVisible(true);
                    setActiveTab(String(index));
                    buttonRef.current?.blur(); 
                  }}
                >
                  {content.icon}
                </Button>
              </Tooltip>
            ))
          )}
          
          <Tooltip 
            title='Metadata Datasets' 
            placement='left'
          >
            <Button
              ref={buttonRef}
              size='large'
              className={`drawer-toggle-btn ${activeTab === String('metadatadataset') && 'drawer-toggle-btn--active'}`}
              onClick={(ev) => { 
                if(activeTab === 'metadatadataset') setIsDrawerVisible(false);
                if(!isDrawerVisible && !activeTab) setIsDrawerVisible(true);
                setActiveTab('metadatadataset');
                buttonRef.current?.blur(); 
              }}
            >
              <PlusCircleOutlined />
          </Button>
        </Tooltip>
        </div>
        <Drawer
          className='search-drawer'
          placement='right'
          width={1000}
          visible={isDrawerVisible}
          closable={false}
          mask={false}
        >
          {customContent.length > 0 && (
            customContent.map((content: CustomContentType,index: number) => {
              if(activeTab === String(index)){
                return cloneElement(content.content, { key: index });
              }
              return null;
            })
          )}

          {activeTab === String('metadatadataset') && (
            <RepoTable
              repo={repo}
              columns={columns}
              pagination={{
                defaultPageSize: 13,
                showSizeChanger: true,
                pageSizeOptions: ['10', '13', '20', '50', '100']
              }}
            />
          )}
        </Drawer>
      </>
    );
};
