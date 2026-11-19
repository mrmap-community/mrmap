import type { RelationGroup } from "./RecordRelations";

import { type ReactElement } from "react";
import {
  AutocompleteInput,
  Create,
  SaveButton,
  SimpleForm,
  required,
  useNotify,
  useRefresh,
  useResourceDefinition,
  useTranslate,
  type RaRecord,
} from "react-admin";
import { useWatch } from "react-hook-form";

import AddIcon from "@mui/icons-material/Add";
import { Button, Typography } from "@mui/material";

import GlobalFormError from "../../../../jsonapi/components/GlobalFormError";
import SchemaAutocompleteInput from "../../../../jsonapi/components/SchemaAutocompleteInput";
import ContextBasedDialog from "../../../Dialog/Dialog";
import {
  DialogBase,
  useDialogContextBase,
} from "../../../Dialog/DialogContextBase";
import DialogHeader from "../../../Dialog/DialogHeader";

const RELATION_RESOURCE = "MetadataRelation";

export interface RecordRelationCreateProps {
  /** the member of a write body which the screen's own record fills */
  ownColumn: string;
  /** the record the screen shows: one end of every coupling it declares */
  record: RaRecord;
  /** the couplings a curator of this screen may declare, with their labels */
  groups: RelationGroup[];
}

/** The kind whose list the partner picker asks: the choice answers the column
 * of the row, so the input is keyed to it and can never ask the list of the
 * wrong kind. The json:api input stores a chosen record as `{ id }`, which is
 * exactly the relationship linkage a declaration sends (#985). */
const PartnerInput = ({ groups }: { groups: RelationGroup[] }) => {
  const kind = useWatch({ name: "kind" }) as string | undefined;
  const group = groups.find((candidate) => candidate.source === kind);
  if (group === undefined) return null;
  return (
    <SchemaAutocompleteInput
      // a chosen kind is a different list to ask, so the picker starts fresh
      key={group.source}
      source="target"
      reference={group.resource}
      label="recordShow.partner"
      helperText={group.edge}
      validate={[required()]}
    />
  );
};

/** The actions row of the dialog: the create the shared dialog performs, with
 * the answers this screen needs. Overriding the success answer of a create
 * replaces what react-admin would have done, so this states the notification
 * itself and asks the whole screen again: the pair is published inside the
 * declaring record's document, so more than the list of rows changed (#985). */
const DeclareActions = () => {
  const { close } = useDialogContextBase();
  const notify = useNotify();
  const refresh = useRefresh();
  return (
    <SaveButton
      // the actions row is rendered by the dialog, out of any form element, so
      // it asks the form itself — the posture of the shared dialog's actions
      type="button"
      // the kind and the partner are all the row states, so the create is
      // complete as soon as they answer
      alwaysEnable
      mutationOptions={{
        onSuccess: () => {
          close();
          notify("recordShow.declared", { type: "success" });
          refresh();
        },
      }}
    />
  );
};

const DeclareButton = () => {
  const translate = useTranslate();
  const { open } = useDialogContextBase();
  return (
    <Button
      size="small"
      variant="outlined"
      startIcon={<AddIcon />}
      aria-haspopup="dialog"
      onClick={() =>
        open(
          <DialogHeader>
            {translate("recordShow.declareRelation")}
          </DialogHeader>,
          null,
          <DeclareActions />,
        )
      }
    >
      {translate("recordShow.declareRelation")}
    </Button>
  );
};

/** The two choices as the row the api writes: the member of the chosen kind
 * carries the partner, the member of the screen's own record carries that
 * record, and the two form fields themselves are the screen's — `kind` and
 * `target` are no members of the schema, so nothing but the relationships
 * travels (#985). */
export const relationRow = (
  values: Record<string, unknown>,
  ownColumn: string,
  ownId: RaRecord["id"],
): Record<string, unknown> => {
  const { kind, target, ...rest } = values;
  return kind == null || typeof kind !== "string"
    ? rest
    : { ...rest, [ownColumn]: { id: ownId }, [kind]: target };
};

/** The body of the declaration dialog: the create of the resource, whose two
 * fields are the curator's choices — the kind of the coupling and its partner.
 * The row the api writes has one more member, the record the screen shows, and
 * the transform answers it from that record: the two choices are the form's,
 * never the api's, so nothing but the relationship members of the schema
 * travels. The form is the shared dialog itself, which mounts nothing while it
 * is closed — so the partner picker asks a list of its kind only once a curator
 * opened the declaration. */
const Declaration = ({
  ownColumn,
  record,
  groups,
}: RecordRelationCreateProps): ReactElement => {
  const translate = useTranslate();
  const { options } = useResourceDefinition({ resource: RELATION_RESOURCE });
  // the row the create writes, from the two choices of the curator
  const toRow = (values: RaRecord) => relationRow(values, ownColumn, record.id);
  return (
    <>
      <DeclareButton />
      <Create
        resource={RELATION_RESOURCE}
        redirect={false}
        // the dialog is the form's component and renders in a portal of its
        // own out of the hidden wrapper — the posture of the shared create
        sx={{ display: "none !important" }}
        transform={toRow}
        mutationOptions={{ meta: { type: options?.type } }}
      >
        <SimpleForm
          component={ContextBasedDialog}
          toolbar={false}
          defaultValues={{ kind: groups[0]?.source }}
        >
          <GlobalFormError />
          <AutocompleteInput
            source="kind"
            label="recordShow.partnerKind"
            choices={groups.map((group) => ({
              id: group.source,
              name: group.edge ?? group.resource,
            }))}
            optionText="name"
            translateChoice={false}
          />
          <PartnerInput groups={groups} />
          <Typography variant="body2" color="text.secondary">
            {translate("recordShow.declareHint", {
              record: record.title ?? record.id,
            })}
          </Typography>
        </SimpleForm>
      </Create>
    </>
  );
};

/** The declaration of one coupling, as the shared create dialog renders it: the
 * offer of the screen and, behind it, one dialog instance of the shared
 * scaffolding.
 *
 * `CreateDialogButton` and `CreateGuesser` were read first and do not fit: they
 * render the whole create schema of MetadataRelation, which is seven
 * relationship pickers of every kind the model knows with no word about the
 * record the curator is standing on, while this screen knows both that record
 * and the kinds a coupling of it can take. What is reused is what those two are
 * built of: `DialogBase`, `Create`, `SaveButton`, `GlobalFormError` and the
 * schema-driven `SchemaAutocompleteInput`; the create travels the data
 * provider's relationship linkage like they do. */
const RecordRelationCreate = (
  props: RecordRelationCreateProps,
): ReactElement => (
  <DialogBase>
    <Declaration {...props} />
  </DialogBase>
);

export default RecordRelationCreate;
