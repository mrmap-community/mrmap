import { ComponentProps, useEffect, useMemo, useRef, useState } from "react";
import {
  useNotify,
  useRecordContext,
  useResourceContext,
  useTranslate,
  useUpdate,
} from "react-admin";

import { Editor } from "@monaco-editor/react";
import SaveIcon from "@mui/icons-material/Save";
import { Alert, Button, GlobalStyles, Stack, Typography } from "@mui/material";

import SimpleCard from "../../../MUI/SimpleCard";
import { changedLinesOf } from "./changedLines";

/**
 * The metadata editor's XML source screen (#1247).
 *
 * Shows the ISO document served for the record — the same bytes the Documents
 * card offers as a download — editable with line numbers and XML syntax
 * highlighting, and writes the curator's text back as the ordinary json:api
 * PATCH of the record's `xmlBackupFile` attribute: no bespoke endpoint
 * (design review of #1238). The backend validates before anything commits
 * (#1243): a refused write lists its json:api error details here and changed
 * nothing; an accepted write becomes the served document, its header the
 * row's, and the fields the form maps are re-extracted from the submitted
 * text — which is why the hint below is part of the screen.
 *
 * Reuse note: no existing card renders an editable text document —
 * `RecordDocuments` only links the stored file (reused for the download),
 * and the OWS context dialog's editor is bound to its own dialog context.
 * This is the editor placed under `MetadataEditor/` so the editor shell of
 * #1245 can embed it.
 */

type EditorProps = ComponentProps<typeof Editor>;
type OnMount = NonNullable<EditorProps["onMount"]>;

// monaco styles its decorations from the page; the class lives with the screen
const CHANGED_LINE_CLASS = "xml-source-changed-line";

type ServerErrors = {
  body?: { errors?: Record<string, string | { serverError: string }> };
};

const failureDetails = (error: unknown): string[] => {
  const errors = (error as ServerErrors | undefined)?.body?.errors;
  const details = Object.values(errors ?? {}).map((value) =>
    typeof value === "string" ? value : value.serverError,
  );
  return details.length > 0
    ? details
    : [((error as Error | undefined)?.message ?? String(error))];
};

const XmlSourceDocument = () => {
  const record = useRecordContext();
  const resource = useResourceContext();
  const translate = useTranslate();
  const notify = useNotify();
  const [update, { isPending }] = useUpdate();
  const [base, setBase] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const [failures, setFailures] = useState<string[]>([]);
  const editorRef = useRef<Parameters<OnMount>[0] | null>(null);
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null);
  const decorationsRef = useRef<
    | ReturnType<Parameters<OnMount>[0]["createDecorationsCollection"]>
    | null
  >(null);

  const url =
    typeof record?.xmlBackupFile === "string" ? record.xmlBackupFile : null;
  const canEdit = record?.canEdit === true;

  // the editor shows the stored bytes — the same the download offers; after a
  // save the record answers a new url and the effect loads what serves now
  // (the submitted text with the header the backend forced)
  useEffect(() => {
    setBase(null);
    setText("");
    setLoadFailed(false);
    if (!url) return;
    let open = true;
    fetch(url)
      .then((response) =>
        response.ok
          ? response.text()
          : Promise.reject(new Error(String(response.status))),
      )
      .then((body) => {
        if (!open) return;
        setBase(body);
        setText(body);
      })
      .catch(() => {
        if (open) setLoadFailed(true);
      });
    return () => {
      open = false;
    };
  }, [url]);

  const changed = useMemo(
    () => (base === null ? [] : changedLinesOf(base, text)),
    [base, text],
  );
  const dirty = base !== null && text !== base;

  // mark the lines the alignment cannot explain against the served document
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    if (!decorationsRef.current) {
      decorationsRef.current = editor.createDecorationsCollection([]);
    }
    decorationsRef.current.set(
      changed.map((line) => ({
        range: new monaco.Range(line, 1, line, 1),
        options: { className: CHANGED_LINE_CLASS, isWholeLine: true },
      })),
    );
  }, [changed]);

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
  };

  const save = () => {
    if (!record || !resource) return;
    setFailures([]);
    update(
      resource,
      {
        id: record.id,
        data: { xmlBackupFile: text },
        previousData: record,
      },
      {
        onSuccess: () => {
          // the invalidation brings the record with its new document url —
          // the effect above reloads the bytes which serve now
          notify("recordShow.sourceSaved", { type: "success" });
        },
        onError: (error: unknown) => setFailures(failureDetails(error)),
      },
    );
  };

  if (!record) return null;
  return (
    <SimpleCard title={translate("recordShow.xmlSource")}>
      <GlobalStyles
        styles={{
          [`.${CHANGED_LINE_CLASS}`]: {
            backgroundColor: "rgba(255, 152, 0, 0.18) !important",
          },
        }}
      />
      <Stack spacing={1}>
        <Typography variant="body2" color="text.secondary">
          {translate("recordShow.sourceHint")}
        </Typography>
        {!canEdit && (
          <Alert severity="info">{translate("recordShow.sourceReadOnly")}</Alert>
        )}
        {loadFailed && (
          <Alert severity="error">
            {translate("recordShow.sourceLoadFailed")}
          </Alert>
        )}
        {failures.length > 0 && (
          <Alert severity="error" data-testid="source-errors">
            {failures.map((detail) => (
              <Typography key={detail} variant="body2">
                {detail}
              </Typography>
            ))}
          </Alert>
        )}
        {url ? (
          <>
            <Editor
              height="60vh"
              defaultLanguage="xml"
              language="xml"
              value={text}
              onChange={(value) => setText(value ?? "")}
              onMount={handleMount}
              options={{
                readOnly: !canEdit,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                renderLineHighlight: "none",
                fontSize: 13,
              }}
            />
            <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
              <Button
                variant="contained"
                startIcon={<SaveIcon />}
                onClick={save}
                disabled={!canEdit || !dirty || isPending}
              >
                {translate("recordShow.sourceSave")}
              </Button>
              <Button onClick={() => setText(base ?? "")} disabled={!dirty}>
                {translate("recordShow.sourceDiscard")}
              </Button>
              <Typography variant="body2" color="text.secondary">
                {translate("recordShow.sourceChangedLines", {
                  count: changed.length,
                })}
              </Typography>
            </Stack>
          </>
        ) : (
          !loadFailed && (
            <Alert severity="info">
              {translate("recordShow.noStoredXml")}
            </Alert>
          )
        )}
      </Stack>
    </SimpleCard>
  );
};

export default XmlSourceDocument;
