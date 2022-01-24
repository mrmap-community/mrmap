import { Button, Drawer, Tooltip } from 'antd';
import React, { cloneElement, ReactElement, useEffect, useRef, useState } from 'react';
import './SearchDrawer.css';

export interface DrawerContentType {
  title: string; 
  icon: ReactElement, 
  isVisible: boolean; 
  content: ReactElement, 
  onTabCickAction: () => void;
  key?: string;
}

export const SearchDrawer = ({
  drawerContent=[],
  isVisibleByDefault=false,
  defaultOpenTab = '',
}:{
  drawerContent?: DrawerContentType[] | never[];
  isVisibleByDefault?: boolean;
  defaultOpenTab?: string
}): ReactElement => {

    const [activeTab, setActiveTab] = useState<string>('');
    const [isDrawerVisible, setIsDrawerVisible] = useState<boolean>(false);
    const buttonRef = useRef<HTMLButtonElement>(null);
    
    useEffect(() => {
      if(!isDrawerVisible) {
        setActiveTab('');
      }
    }, [isDrawerVisible]);

    useEffect(() => {
      if(isVisibleByDefault) {
        setIsDrawerVisible(true);
      }
    }, [isVisibleByDefault]);

    useEffect(() => {
      if(defaultOpenTab) {
        setActiveTab(defaultOpenTab);
        setIsDrawerVisible(true);
      }
    }, [defaultOpenTab]);

    return (
      <>
        <div className={`drawer-toggle-tabs ${isDrawerVisible ? 'expanded' : 'collapsed'}`}>
          {drawerContent.length > 0 && (
            drawerContent.map((content:DrawerContentType, index: number) => (
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
                    if(content.key) {
                      setActiveTab(content.key);
                    } else {
                      setActiveTab(String(index));
                    }
                    if(activeTab === String(index) || activeTab === content.key){
                      setIsDrawerVisible(false);
                    }
                    if(!isDrawerVisible && !activeTab) setIsDrawerVisible(true);
                    buttonRef.current?.blur(); 
                  }}
                >
                  {content.icon}
                </Button>
              </Tooltip>
            ))
          )}
        </div>
        <Drawer
          className='search-drawer'
          placement='right'
          width={1000}
          visible={isDrawerVisible}
          closable={false}
          mask={false}
        >
          {drawerContent.length > 0 && (
            drawerContent.map((content: DrawerContentType,index: number) => {
              if(activeTab === content.key || activeTab === String(index)){
                return cloneElement(content.content, { key: content.content ? content.key : index });
              }
              return null;
            })
          )}
        </Drawer>
      </>
    );
};
