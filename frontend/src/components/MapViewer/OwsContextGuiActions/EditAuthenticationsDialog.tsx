import { useEffect, useState } from "react";
import { useTranslate } from "react-admin";

import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { v4 as uuidv4 } from "uuid";

import { resolveOperationAuthentication } from "../../../ows-lib/OwsContext/authentication";
import { OWSContext } from "../../../ows-lib/OwsContext/core";
import { isWfsOfferingCode, isWmsOfferingCode } from "../../../ows-lib/OwsContext/validation";
import { useOwsContextBase } from "../../../react-ows-lib/ContextProvider/OwsContextBase";

export interface EditAuthenticationsDialogProps {
  open: boolean;
  setOpen: (open: boolean) => void;
  folder?: string;
}

const EditAuthenticationsDialog = ({
  open,
  setOpen,
  folder,
}: EditAuthenticationsDialogProps) => {
  const { owsContext, updateOwsContext } = useOwsContextBase();
  const translate = useTranslate();
  const t = (key: string) => translate(`viewerAuth.${key}`);
  const [draft, setDraft] = useState(() =>
    OWSContext.fromPlainObject(owsContext),
  );
  const [origin, setOrigin] = useState("");
  const [name, setName] = useState("Authorization");
  const [value, setValue] = useState("");
  const [mode, setMode] = useState("header");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!open) return;
    const next = OWSContext.fromPlainObject(owsContext);
    next.authenticationHeaders = (next.authenticationHeaders ?? []).map(
      (auth) => ({ ...auth }),
    );
    setDraft(next);
    setOrigin("");
    setName("Authorization");
    setValue("");
    setUsername("");
    setPassword("");
    setMode("header");
    setError(false);
  }, [open, owsContext]);
  const refresh = () => setDraft(OWSContext.fromPlainObject(draft));
  const add = () => {
    try {
      const url = new URL(origin);
      const headerName = mode === "basic" ? "Authorization" : name;
      const headerValue =
        mode === "basic" ? `Basic ${btoa(`${username}:${password}`)}` : value;
      if (
        !["https:", "http:"].includes(url.protocol) ||
        !headerName.trim() ||
        !headerValue ||
        (mode === "basic" && !username)
      )
        throw new Error();
      new Headers({ [headerName]: headerValue });
      draft.authenticationHeaders = [
        ...(draft.authenticationHeaders ?? []),
        {
          id: uuidv4(),
          type: "header",
          origin: url.origin,
          name: headerName,
          value: headerValue,
        },
      ];
      refresh();
      setValue("");
      setPassword("");
      setError(false);
    } catch {
      setError(true);
    }
  };
  return (
    <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
      <DialogTitle>{t("title")}</DialogTitle>
      <DialogContent>
        <Stack spacing={2}>
          <Alert severity="info">{t("session")}</Alert>
          {(draft.authenticationHeaders ?? []).map((auth) => (
            <Stack key={auth.id} spacing={1}>
              <Typography>
                {auth.origin} · {auth.name}
              </Typography>
              <TextField
                label={t("secret")}
                type="password"
                value={auth.value ?? ""}
                onChange={(event) => {
                  draft.authenticationHeaders =
                    draft.authenticationHeaders?.map((entry) =>
                      entry.id === auth.id
                        ? { ...entry, value: event.target.value }
                        : entry,
                    );
                  refresh();
                }}
              />
              <Button
                onClick={() => {
                  draft.authenticationHeaders =
                    draft.authenticationHeaders?.filter(
                      (entry) => entry.id !== auth.id,
                    );
                  // Retain references so missing credentials are visible and requests are blocked.
                  refresh();
                }}
              >
                {t("delete")}
              </Button>
            </Stack>
          ))}
          <TextField
            label={t("origin")}
            value={origin}
            onChange={(event) => setOrigin(event.target.value)}
          />
          <TextField
            select
            label={t("method")}
            value={mode}
            onChange={(event) => setMode(event.target.value)}
          >
            <MenuItem value="header">{t("header")}</MenuItem>
            <MenuItem value="basic">Basic</MenuItem>
          </TextField>
          {mode === "basic" ? (
            <>
              <TextField
                label={t("username")}
                value={username}
                onChange={(event) => setUsername(event.target.value)}
              />
              <TextField
                label={t("password")}
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </>
          ) : (
            <>
              <TextField
                label={t("header")}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
              <TextField
                label={t("newSecret")}
                type="password"
                value={value}
                onChange={(event) => setValue(event.target.value)}
              />
            </>
          )}
          {error && <Alert severity="error">{t("invalid")}</Alert>}
          <Button onClick={add}>{t("add")}</Button>
          {draft.features
            .filter(
              (feature) =>
                folder === undefined ||
                feature.properties.folder === folder ||
                feature.properties.folder?.startsWith(`${folder}/`),
            )
            .map((feature) =>
              (feature.properties.offerings ?? [])
                .filter((offering) => isWmsOfferingCode(offering.code) || isWfsOfferingCode(offering.code))
                .map((offering, offeringIndex) =>
                  (offering.operations ?? []).map(
                    (operation, operationIndex) => {
                      const id = operation["x-authentication-id"];
                      const authError = resolveOperationAuthentication(
                        draft,
                        operation,
                      ).error;
                      const label = `${feature.properties.title} · ${operation.code} · ${new URL(operation.href).origin}`;
                      return (
                        <TextField
                          select
                          key={`${feature.properties.folder}:${offeringIndex}:${operationIndex}`}
                          label={label}
                          value={typeof id === "string" ? id : ""}
                          error={Boolean(authError)}
                          helperText={authError ? t(authError) : undefined}
                          onChange={(event) => {
                            if (event.target.value)
                              operation["x-authentication-id"] =
                                event.target.value;
                            else delete operation["x-authentication-id"];
                            refresh();
                          }}
                        >
                          <MenuItem value="">{t("none")}</MenuItem>
                          {id !== undefined &&
                            !draft.authenticationHeaders?.some(
                              (auth) =>
                                auth.id === id &&
                                auth.origin === new URL(operation.href).origin,
                            ) && (
                              <MenuItem value={String(id)}>
                                {t("missing")}
                              </MenuItem>
                            )}
                          {(draft.authenticationHeaders ?? [])
                            .filter(
                              (auth) =>
                                auth.origin === new URL(operation.href).origin,
                            )
                            .map((auth) => (
                              <MenuItem key={auth.id} value={auth.id}>
                                {auth.origin} · {auth.name} ·{" "}
                                {auth.id.slice(0, 8)}
                              </MenuItem>
                            ))}
                        </TextField>
                      );
                    },
                  ),
                ),
            )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>{t("cancel")}</Button>
        <Button
          onClick={() => {
            const result = updateOwsContext(draft);
            if (!result?.hasErrors) setOpen(false);
          }}
        >
          {t("save")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default EditAuthenticationsDialog;
