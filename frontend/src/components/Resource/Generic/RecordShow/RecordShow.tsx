import {
  Show,
  TabbedShowLayout,
  useResourceContext,
  useTranslate,
} from "react-admin";
import ServiceShowTabs from "../ServiceShowTabs";
import RecordHeader from "./RecordHeader";
import RecordOverview from "./RecordOverview";
import RecordSpatial from "./RecordSpatial";
import RecordContacts from "./RecordContacts";
import RecordRelations from "./RecordRelations";
import RecordHistory from "./RecordHistory";

const RecordShow = () => {
  const resource = useResourceContext();
  const translate = useTranslate();
  const include = [
    "metadataContact",
    "licence",
    "keywords",
    "referenceSystems",
    "timeExtents",
    "languages",
    "harvestedThrough",
    "createdBy",
    "lastModifiedBy",
    ...(resource === "DatasetMetadataRecord"
      ? ["datasetContact", "categories"]
      : []),
  ].join(",");
  return (
    <Show
      actions={false}
      queryOptions={{
        meta: {
          jsonApiParams: {
            include,
            "fields[CatalogueService]": "title,string_representation",
          },
        },
      }}
    >
      <RecordHeader />
      <TabbedShowLayout tabs={<ServiceShowTabs />}>
        <TabbedShowLayout.Tab label={translate("recordShow.overview")}>
          <RecordOverview />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab
          path="spatial"
          label={translate("recordShow.spatial")}
        >
          <RecordSpatial />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab
          path="contacts"
          label={translate("recordShow.contacts")}
        >
          <RecordContacts />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab
          path="relations"
          label={translate("recordShow.relations")}
        >
          <RecordRelations />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab
          path="harvests"
          label={translate("recordShow.harvests")}
        >
          <RecordHistory harvests />
        </TabbedShowLayout.Tab>
        <TabbedShowLayout.Tab
          path="history"
          label={translate("recordShow.history")}
        >
          <RecordHistory />
        </TabbedShowLayout.Tab>
      </TabbedShowLayout>
    </Show>
  );
};

export default RecordShow;
