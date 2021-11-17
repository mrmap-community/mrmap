import { Card } from "antd";
import Form from "@rjsf/antd";

export const ServiceEdit = () => {

    const schema = {
        title: "Test form",
        type: "object",
        properties: {
          name: {
            type: "string"
          },
          age: {
            type: "number"
          },
          birthday: {
            type: "string",
            format: "date"
          },
          numbers: {
            "type": "array",
            "items": {
              "type": "number"
            }
          }
        }
      };

    // const uiSchema = {
    //     classNames: "custom-css-class"
    // };
    return (
        <Card title="Create/Edit Service" style={{ width: '100%' }}>
            <Form schema={schema} />
        </Card>
    );
}
