import {
  Show,
  TabbedShowLayout,
  useResourceContext,
  useTranslate,
} from "react-admin";

import useOperation from "../../../../jsonapi/hooks/useOperation";
import ServiceShowTabs from "../ServiceShowTabs";
import RecordContacts from "./RecordContacts";
import RecordDocuments from "./RecordDocuments";
import RecordHeader from "./RecordHeader";
import RecordHistory from "./RecordHistory";
import RecordOverview from "./RecordOverview";
import RecordRelations from "./RecordRelations";
import RecordSpatial from "./RecordSpatial";

// the contact which provides the record is named after the kind of record; the
// application record (see the model docstring of ApplicationMetadataRecord) carries
// its own one in place of the dataset contact
const PROVIDING_CONTACT: Record<string, string> = {
  DatasetMetadataRecord: "datasetContact",
  ApplicationMetadataRecord: "applicationContact",
};

// the documents tab is offered by the resource screens which ask for it: the
// application record is harvested as an xml document and the screen shows the
// stored answer (the dataset and service screens stay as they are)
const RecordShow = ({ documents = false }: { documents?: boolean }) => {
  const resource = useResourceContext();
  const translate = useTranslate();
  const providingContact = PROVIDING_CONTACT[resource ?? ""];
  // the changelog tab exists exactly where the schema answers the historical
  // records of the resource, as the history route of the resource does
  const historicalOperation = useOperation(`list_Historical${resource ?? ""}`);
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
    ...(providingContact ? [providingContact, "categories"] : []),
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
        {documents && (
          <TabbedShowLayout.Tab
            path="documents"
            label={translate("recordShow.documents")}
          >
            <RecordDocuments />
          </TabbedShowLayout.Tab>
        )}
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
        {historicalOperation && (
          <TabbedShowLayout.Tab
            path="history"
            label={translate("recordShow.history")}
          >
            <RecordHistory />
          </TabbedShowLayout.Tab>
        )}
      </TabbedShowLayout>
    </Show>
  );
};

export default RecordShow;
