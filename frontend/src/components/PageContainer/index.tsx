import type { PageContainerProps as ProPageContainerProps } from "@ant-design/pro-layout";
import { PageContainer as ProPageContainer } from "@ant-design/pro-layout";
import type { ReactElement } from "react";
import { useMemo } from "react";
import { useIntl, useParams } from "umi";

export interface PageContainerProps extends ProPageContainerProps {
    children: ReactElement;
}


const GenericPageContainer = (props: PageContainerProps): ReactElement => {
    const intl = useIntl();
    const { id } = useParams<{ id: string }>();
    
    const title = useMemo(() => {
        const pathname = window.location.pathname;
        const routes = pathname.split('/');
        routes.shift(); // to remove first empty string

        const defaultMessage = routes[routes.length - 1];

        if (id){
            const indexOfId = routes.indexOf(id);

            if (routes.length > indexOfId) {
                const firstChar = routes[indexOfId+1].charAt(0);
                if (firstChar === firstChar.toLocaleUpperCase()){
                    // its a nested route with the resource type in route definition
                    return intl.formatMessage(
                        { 
                            id: `title.${routes[0]}.${routes[indexOfId-1]}.nested.${routes[indexOfId+1]}`,
                            defaultMessage: defaultMessage
                        }, 
                        { id: id}
                    );
                } else {
                    // its a action route with the action name in route definition
                    return intl.formatMessage(
                        { 
                            id: `title.${routes[0]}.${routes[indexOfId+1]}.${routes[indexOfId-1]}`,
                            defaultMessage: defaultMessage
                        }, 
                        { id: id}
                    );
                }
                
                
            } else {
                // its a details page
                return intl.formatMessage(
                    { 
                        id: `title.${routes[0]}.details.${routes[indexOfId-1]}`,
                        defaultMessage: defaultMessage,
                    }, 
                    { id: id}
                );
            }

        } else {
            // its a simple list
            return intl.formatMessage(
                { 
                    id: `menu.${routes[0]}.${routes[routes.length - 1]}`,
                    defaultMessage: defaultMessage,
                }
            );
        }
    }, [id, intl]);
  
    
    return (
        <ProPageContainer 
            title={props.title || title} 
            {...props}
        />
    );
  };
  
  export default GenericPageContainer;
  