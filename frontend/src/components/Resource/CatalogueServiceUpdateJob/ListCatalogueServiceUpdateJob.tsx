import { type ReactNode } from "react";
import {
  DateField,
  FunctionField,
  TextField,
  useTranslate,
} from "react-admin";

import { Typography } from "@mui/material";

import ListWithDialogs from "../../../jsonapi/components/ListWithDialogs";
import JsonApiReferenceField from "../../../jsonapi/components/ReferenceField";
import CustomListActions, {
  type CustomListActionsProps,
} from "../../Lists/CustomListActions";
import { UpdateJobStatusChip, waitsFor } from "./UpdateJobState";

/** the rows of this screen are the jobs of a deployment, and those are many */
const PER_PAGE = 25;

/**
 * The columns of this screen are the questions about a job, so none of them is
 * chosen: the screen of a job answers everything else.
 */
const FixedColumnsActions = (props: CustomListActionsProps) => (
  <CustomListActions {...props} isConfigureable={false} />
);

/**
 * The update jobs of the catalogues of a deployment.
 *
 * The update of a catalogue is the decision which applies the metadata a
 * catalogue reports about itself, so a row names the catalogue the job belongs
 * to, the state the job is in, the moment it ended and what it waits for while
 * it did not. All of it is answered by the endpoint of the jobs: the catalogue
 * as the relationship a job is made of, the state as the name the api answers
 * it with. The row opens the job it shows a row of, because the decision which
 * follows a harvest is asked about at the job and not in a table of them.
 */
const ListCatalogueServiceUpdateJob = (): ReactNode => {
  const translate = useTranslate();
  return (
    <ListWithDialogs
      listGuesserProps={{
        resource: "CatalogueServiceUpdateJob",
        perPage: PER_PAGE,
        // the newest job is the one which decides about a catalogue now, and
        // the endpoint answers this sort of its own accord
        sort: { field: "dateCreated", order: "DESC" },
        ActionsComponent: FixedColumnsActions,
        columns: [
          <TextField key="id" source="id" />,
          <JsonApiReferenceField
            key="service"
            source="service"
            reference="CatalogueService"
            sortable={false}
            sx={{ overflowWrap: "anywhere" }}
          />,
          <FunctionField
            key="status"
            source="status"
            render={() => <UpdateJobStatusChip />}
          />,
          <DateField
            key="doneAt"
            source="doneAt"
            showTime
            emptyText={translate("resources.CatalogueServiceUpdateJob.running")}
          />,
          <FunctionField
            key="waitsFor"
            label="resources.CatalogueServiceUpdateJob.columns.waitsFor"
            sortable={false}
            render={(record) => {
              const waiting = waitsFor(record, translate);
              return (
                <Typography
                  variant="body2"
                  color={waiting ? undefined : "text.secondary"}
                >
                  {waiting ?? "—"}
                </Typography>
              );
            }}
          />,
        ],
        dataGridProps: {
          rowClick: "show",
          sx: {
            "& .RaDatagrid-headerCell": { whiteSpace: "nowrap" },
            "& .column-service": { minWidth: 180, maxWidth: 320 },
          },
        },
      }}
    />
  );
};

export default ListCatalogueServiceUpdateJob;
