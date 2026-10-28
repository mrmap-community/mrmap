import { type ReactNode } from "react";
import {
  type RaRecord,
  SaveButton,
  ShowButton,
  Toolbar,
  useResourceDefinition,
  useTranslate,
} from "react-admin";

import AddIcon from "@mui/icons-material/Add";
import { Alert, Button, Stack, Typography } from "@mui/material";

import CreateGuesser from "../../../../jsonapi/components/CreateGuesser";
import useGuesserSuccess from "../../../../jsonapi/hooks/useGuesserSuccess";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import CandidateHints from "./CandidateHints";
import {
  deliveringResourceOfTarget,
  registeredTargetResource,
  resourceOfService,
  type CandidateValidation,
  type RegisteredTarget,
  type ServiceCandidate,
} from "./useServiceCandidates";

/** One selected candidate as the resource its endpoint delivers. */
export interface RegistrationTarget {
  /** The json:api resource whose create schema registers the endpoint. */
  resource: string;
  candidate: ServiceCandidate;
  /** The answer of the endpoint, when the user asked it. */
  answer?: CandidateValidation;
}

/** What speaks against registering the selected candidate. */
type Refusal = "unknownService" | "unsupportedService" | "refused";

/**
 * What the registry can do with a selected candidate.
 *
 * The resource is decided by what the endpoint announced, because a record may
 * advertise an endpoint as something else than what it delivers; without an
 * answer the token the record wrote is the only evidence and stays a promise.
 * An endpoint which refused or did not answer is never offered: registering it
 * would only queue a task which cannot finish.
 */
const registrationOf = (
  candidate: ServiceCandidate | undefined,
  answer?: CandidateValidation,
): RegistrationTarget | { refusal: Refusal } | undefined => {
  if (!candidate) return undefined;
  if (answer && ["unsupported", "unavailable"].includes(answer.state))
    return { refusal: "refused" };
  const token = answer?.service_type ?? candidate.service;
  const resource = resourceOfService(token);
  if (!resource)
    return { refusal: token ? "unsupportedService" : "unknownService" };
  return { resource, candidate, answer };
};

const Reason = ({
  refusal,
  token,
}: {
  refusal: Refusal;
  token?: string | null;
}) => {
  const translate = useTranslate();
  return (
    <Typography variant="caption" color="text.secondary">
      {translate(`serviceCandidates.registration.${refusal}`, { token })}
    </Typography>
  );
};

export interface CandidateRegistrationButtonProps {
  /** The selected candidate; nothing is offered without one. */
  candidate?: ServiceCandidate;
  /** What its endpoint answered, when it was asked. */
  answer?: CandidateValidation;
  /** Opens the registration step for the candidate. */
  onRegister: (target: RegistrationTarget) => void;
}

/**
 * Offers to register the selected candidate.
 *
 * The action belongs to the resource the endpoint delivers, so the permission
 * gate is asked for that resource and not for the metadata record the dialog
 * shows: reading a record grants nothing over the services it advertises. The
 * api answering a create operation at all is the second gate, so against a
 * backend without service registration no action appears.
 */
export const CandidateRegistrationButton = ({
  candidate,
  answer,
  onRegister,
}: CandidateRegistrationButtonProps): ReactNode => {
  const translate = useTranslate();
  const registration = registrationOf(candidate, answer);
  const resource =
    registration && "resource" in registration
      ? registration.resource
      : undefined;
  const { hasCreate } = useResourceDefinition({ resource });
  const creatable = Boolean(useOperation(`create_${resource}`));

  if (!registration) return null;
  if ("refusal" in registration)
    return (
      <Reason
        refusal={registration.refusal}
        token={answer?.service_type ?? candidate?.service}
      />
    );
  if (!hasCreate || !creatable)
    return (
      <Typography variant="caption" color="text.secondary">
        {translate("serviceCandidates.registration.noRights")}
      </Typography>
    );
  return (
    <Button
      color="primary"
      startIcon={<AddIcon />}
      onClick={() => onRegister(registration)}
    >
      {translate("serviceCandidates.registration.action")}
    </Button>
  );
};

/** One label with the value it belongs to, kept readable when it is a url. */
const SourceLine = ({ label, value }: { label: string; value: ReactNode }) => (
  <Stack
    direction="row"
    useFlexGap
    sx={{ alignItems: "baseline", flexWrap: "wrap", gap: 1 }}
  >
    <Typography variant="caption" color="text.secondary" sx={{ mr: 0 }}>
      {label}
    </Typography>
    <Typography variant="body2" sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
      {value}
    </Typography>
  </Stack>
);

/** The confirmation of the form, on the house notification path of a create. */
const RegistrationToolbar = ({
  resource,
  onRegistered,
}: {
  resource: string;
  onRegistered: () => void;
}) => {
  const notifyCreated = useGuesserSuccess({
    resource,
    action: "created",
    // the resource is created by the task, so there is nothing to route to
    redirectTo: false,
    undoable: false,
  });
  return (
    <Toolbar>
      {/* a button of type "submit" may not carry mutationOptions: react-admin
          only honours them on a button which saves on its own click */}
      <SaveButton
        mutationOptions={{
          onSuccess: (record: RaRecord) => {
            notifyCreated(record);
            onRegistered();
          },
        }}
        type="button"
        alwaysEnable
      />
    </Toolbar>
  );
};

export interface CandidateRegistrationFormProps {
  /** The candidate to register and the resource it delivers. */
  target: RegistrationTarget;
  /** What the record already delivers through a registered resource. */
  registered: RegisteredTarget[];
  /** The record the candidates were resolved for, as its screen names it. */
  sourceRecord?: ReactNode;
  /** The identifier the stored document names itself by. */
  sourceDocument?: string | null;
  /** Closes the flow once the registration was taken. */
  onRegistered: () => void;
}

/**
 * The existing create form of a service, taken from a candidate.
 *
 * Nothing here registers anything by itself: the form is the schema driven
 * `CreateGuesser` of the resource, which asks the same create endpoint the list
 * screen offers, keeps its validation, its organization owner and credentials
 * fields and answers a background task instead of a finished service. Only the
 * capabilities endpoint is filled in, from what the endpoint itself answered.
 */
export const CandidateRegistrationForm = ({
  target,
  registered,
  sourceRecord,
  sourceDocument,
  onRegistered,
}: CandidateRegistrationFormProps): ReactNode => {
  const translate = useTranslate();
  const t = (key: string, args?: Record<string, unknown>) =>
    translate(`serviceCandidates.registration.${key}`, args);
  const { candidate, answer, resource } = target;
  // the answered url names service, request and version as the create
  // serializer asks for them, the candidate url is the endpoint as advertised
  const url = answer?.registration_url ?? candidate.url;
  // what the record already delivers, seen from the resource this form
  // registers: an element counts as its service, a service of another kind
  // does not make this registration a second one
  const duplicates = registered.filter(
    (item) => deliveringResourceOfTarget(item) === resource,
  );
  return (
    <Stack spacing={2} sx={{ minWidth: 0 }}>
      <Stack spacing={0.5}>
        <Typography variant="subtitle2">{t("source")}</Typography>
        {sourceRecord && (
          <SourceLine label={t("record")} value={sourceRecord} />
        )}
        {sourceDocument && (
          <SourceLine label={t("document")} value={sourceDocument} />
        )}
        <SourceLine label={t("advertised")} value={candidate.original_url} />
        {candidate.url !== candidate.original_url && (
          <SourceLine label={t("capabilities")} value={candidate.url} />
        )}
        {answer?.service_type && (
          <Typography variant="caption" color="text.secondary">
            {answer.service_version
              ? t("answeredVersion", {
                  service: answer.service_type,
                  version: answer.service_version,
                })
              : t("answered", { service: answer.service_type })}
          </Typography>
        )}
        <CandidateHints candidate={candidate} validation={answer} />
      </Stack>
      {duplicates.length > 0 && (
        <Alert severity="warning">
          <Stack spacing={0.5}>
            <Typography variant="body2">{t("duplicate")}</Typography>
            {duplicates.map((item) => (
              <Stack
                key={`${item.resource_type}-${item.id}`}
                direction="row"
                useFlexGap
                sx={{ alignItems: "center", gap: 1 }}
              >
                <Typography
                  variant="body2"
                  sx={{ minWidth: 0, flex: 1, overflowWrap: "anywhere" }}
                >
                  {item.name}
                </Typography>
                <ShowButton
                  resource={registeredTargetResource[item.resource_type]}
                  record={{ id: item.id, name: item.name }}
                  label="ra.action.show"
                  size="small"
                />
              </Stack>
            ))}
            <Typography variant="caption">{t("duplicateHint")}</Typography>
          </Stack>
        </Alert>
      )}
      <CreateGuesser
        resource={resource}
        redirect={false}
        // the dialog names the step already, and the answer above names the
        // service this form registers
        title={false}
        defaultValues={{ getCapabilitiesUrl: url }}
        toolbar={
          <RegistrationToolbar
            resource={resource}
            onRegistered={onRegistered}
          />
        }
      />
    </Stack>
  );
};
