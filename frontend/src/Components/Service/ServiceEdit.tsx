import { Card } from "antd";
import Form from "@rjsf/antd";
import { useContext, useEffect, useState } from "react";
import { OpenAPIContext } from "../../Hooks/OpenAPIProvider";

export const ServiceEdit = () => {

  const { api } = useContext(OpenAPIContext);
  const [schema, setSchema] = useState<any>({
    title: "Test form",
    type: "object",
    properties: {}
  });

  useEffect(() => {
    async function buildSchema() {
      const client = await api.getClient();
      const props = client.api.getOperation("v1_registry_service_services_create").requestBody.content["application/json"].schema.properties;
      console.log(props);
      setSchema({
        type: "object",
        properties: props
      });
    }
    buildSchema();
  }, [api]);

  const handleSubmit = (formData:any) => {
    console.log(formData);
  }

  return (
    <Card title="Create/Edit Service" style={{ width: '100%' }}>
      <Form schema={schema} onSubmit={handleSubmit}/>
    </Card>
  );
}
