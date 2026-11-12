import {
  useRecordContext,
  useResourceContext,
  useTranslate,
  type RaRecord,
} from "react-admin";

import { Grid, Link, Stack } from "@mui/material";

import SimpleCard from "../../../MUI/SimpleCard";
import RecordFields, { IncludedRecordFields } from "./RecordFields";

const Contact = ({ record }: { record?: RaRecord }) => (
  <Stack spacing={1}>
    <IncludedRecordFields
      resource="MetadataContact"
      record={record}
      sources={[
        "name",
        "personName",
        "address",
        "city",
        "postalCode",
        "stateOrProvince",
        "country",
        "facsimile",
      ]}
    />
    {record?.email && (
      <Link href={`mailto:${record.email}`}>{record.email}</Link>
    )}
    {record?.phone && <Link href={`tel:${record.phone}`}>{record.phone}</Link>}
  </Stack>
);

// the contact which provides the record is named after its kind: the dataset
// record names its dataset contact, the application record its application one
const PROVIDING_CONTACT: Record<string, string> = {
  DatasetMetadataRecord: "datasetContact",
  ApplicationMetadataRecord: "applicationContact",
};

const RecordContacts = () => {
  const record = useRecordContext();
  const resource = useResourceContext();
  const translate = useTranslate();
  const providingContact = PROVIDING_CONTACT[resource ?? ""];
  return (
    <Grid container spacing={2}>
      <Grid size={{ xs: 12, md: 6 }}>
        <SimpleCard title={translate("recordShow.metadataContact")}>
          <Contact record={record?.metadataContact} />
        </SimpleCard>
      </Grid>
      {providingContact && (
        <Grid size={{ xs: 12, md: 6 }}>
          <SimpleCard title={translate(`recordShow.${providingContact}`)}>
            <Contact record={record?.[providingContact]} />
          </SimpleCard>
        </Grid>
      )}
      <Grid size={12}>
        <SimpleCard title={translate("recordShow.usage")}>
          <IncludedRecordFields
            resource="Licence"
            record={record?.licence}
            sources={[
              "name",
              "identifier",
              "isOpenData",
              "symbolUrl",
              "descriptionUrl",
            ]}
          />
          <RecordFields
            sources={[
              "accessConstraints",
              "fees",
              "useLimitation",
              "licenseSourceNote",
            ]}
          />
        </SimpleCard>
      </Grid>
    </Grid>
  );
};

export default RecordContacts;
