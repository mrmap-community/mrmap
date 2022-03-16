import { DatabaseOutlined } from '@ant-design/icons';
import ProLayout, { PageContainer } from '@ant-design/pro-layout';
import React from 'react';
import { useNavigate } from 'react-router-dom';

const route = {
  exact: false,
  path: '/',
  component: '@/layouts/index',
  routes: [
    {
      exact: true,
      path: '/',
      component: '@/pages/index',
    },
    {
      path: '/registry',
      name: 'Registry',
      icon: <DatabaseOutlined />,
      routes: [
        {
          path: '/registry/webmapservices',
          name: 'WebMapServices',       
          component: '@/pages/registry/WmsTable'   
        }
      ],
    }
  ],
};

export default function Layout (): JSX.Element {
  const navigate = useNavigate();

  return (
    <div
      id='test-pro-layout'
      style={{
        height: '100vh',
      }}
    >
      <ProLayout 
        title='Mr. Map'
        logo={<img  width='95%' src={process.env.PUBLIC_URL + '/logo.png'} alt='mrmap logo'></img>}
        route={route}
        onMenuHeaderClick={(e) => console.log(e)}
        menuItemRender={(item, dom) => (
          <a
            onClick={() => {
              navigate(item.path || '/');
            }}
          >
            {dom}
          </a>
        )}
        //location={{ location.pathname }}
        // rightContentRender={() => (
        //   <div>
        //     <Avatar shape='square' size='small' icon={<UserOutlined />} />
        //   </div>
        // )}
      >
        <PageContainer>

        </PageContainer>
      </ProLayout>
      
    </div>
  );
}
