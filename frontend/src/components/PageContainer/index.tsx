import type { PageContainerProps as ProPageContainerProps } from "@ant-design/pro-layout";
import { PageContainer as ProPageContainer } from "@ant-design/pro-layout";
import type { ReactElement } from "react";
import { useMemo } from "react";
import { useIntl, useParams } from "umi";

export interface PageContainerProps extends ProPageContainerProps {
    menuPaths: string[];
    children: ReactElement;
}


const PageContainer = (props: PageContainerProps): ReactElement => {

    const intl = useIntl();
    const { id } = useParams<{ id: string }>();
    
    const title = useMemo(() => {
        const pathname = window.location.pathname;
        const routes = pathname.split('/');
        if (id){
            const indexOfId = routes.indexOf(id);
            return intl.formatMessage(
                { id: `menu.${props.menuPaths.join('.')}.nested${routes[indexOfId+1]}For${routes[indexOfId-1]}` }, 
                { id: id}
            )
        } else {
            return intl.formatMessage(
                { id: `menu.${props.menuPaths.join('.')}.${routes[-1]}` },
            )
        }
    }, [id]);
  
    
    return <ProPageContainer title={title} {...props}/>;
  };
  
  export default PageContainer;
  