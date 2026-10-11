import ServiceRelatedTab from "../../Generic/ServiceShow/ServiceRelatedTab";

export default function Settings() {
  return (
    <ServiceRelatedTab
      resource="CatalogueServiceOperationUrl"
      defaultSelectedColumns={["operation", "url", "method"]}
    />
  );
}
