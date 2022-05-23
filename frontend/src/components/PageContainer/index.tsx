import type { PageContainerProps as ProPageContainerProps } from "@ant-design/pro-layout";
import { PageContainer as ProPageContainer } from "@ant-design/pro-layout";
import type { ReactElement } from "react";
import { useMemo } from "react";
import { useIntl, useParams } from "umi";

export interface PageContainerProps extends ProPageContainerProps {
    children: ReactElement;
}


const PageContainer = (props: PageContainerProps): ReactElement => {
    const intl = useIntl();
    const { id } = useParams<{ id: string }>();
    
    const title = useMemo(() => {
        const pathname = window.location.pathname;
        const routes = pathname.split('/');
        routes.shift(); // to remove first empty string
        if (id){
            const indexOfId = routes.indexOf(id);
            return intl.formatMessage(
                { id: `menu.${routes[0]}.nested${routes[indexOfId+1]}For${routes[indexOfId-1]}` }, 
                { id: id}
            )
        } else {
            return intl.formatMessage(
                { id: `menu.${routes[0]}.${routes[routes.length - 1]}` },
            )
        }
    }, [id]);
  
    
    return <ProPageContainer title={title} {...props}/>;
  };
  
  export default PageContainer;
  