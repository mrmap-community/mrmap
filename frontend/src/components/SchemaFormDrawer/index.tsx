import type { JsonApiPrimaryData } from "@/utils/jsonapi";
import type { DrawerProps } from "antd";
import { Drawer } from "antd";
import type { ReactElement } from "react";
import { useState } from "react";
import type { SchemaFormProps } from "../SchemaForm";
import SchemaForm from "../SchemaForm";

interface SchemaFormDrawerProps{
    resourceObject: JsonApiPrimaryData
    drawerProps?: DrawerProps
    schemaFormProps?: SchemaFormProps
}

const SchemaFormDrawer = ({
    resourceObject,
    drawerProps = undefined,
    schemaFormProps = undefined
  }: SchemaFormDrawerProps): ReactElement => {
    
    const [rightDrawerVisible, setRightDrawerVisible] = useState<boolean>(drawerProps?.visible || false);
    const [selectedForEdit] = useState<JsonApiPrimaryData>(resourceObject);

    return (
        <Drawer
            placement="right"
            visible={rightDrawerVisible}
            onClose={() => {
                setRightDrawerVisible(false);
            }}
            {...drawerProps}
        >
            <SchemaForm
                resourceType={selectedForEdit.type}
                resourceId={selectedForEdit.id}
                onSuccess={() => {
                    setRightDrawerVisible(false);
                }}
                {...schemaFormProps}
            />
        </Drawer>
    );
  };
  
  export default SchemaFormDrawer;
  