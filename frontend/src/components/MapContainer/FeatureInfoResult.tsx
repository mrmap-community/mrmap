import { ReactNode, useEffect, useMemo, useState } from "react";
import { useTranslate } from "react-admin";

import ExpandMore from "@mui/icons-material/ExpandMore";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Button,
  Link as MuiLink,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Typography,
} from "@mui/material";

const parseIdentify = (text: string): unknown => {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
};

const entries = (value: unknown) =>
  value && typeof value === "object" && !Array.isArray(value)
    ? Object.entries(value as Record<string, unknown>)
    : [];

/** A feature of an answer with the place it came from, which is what names it in the answer. */
interface IdentifiedFeature {
  place: string;
  value: unknown;
}

const identifyFeatures = (value: unknown): IdentifiedFeature[] | undefined => {
  const features = (value as { features?: unknown })?.features;
  if (!Array.isArray(features)) {
    return undefined;
  }
  return features.map((feature, position) => ({
    place: `feature-${position}`,
    value: feature,
  }));
};

/** A piece of a service answer with the place it was read at, which names it in that answer. */
interface IdentifiedCell {
  place: string;
  text: string;
  header: boolean;
}

interface IdentifiedRow {
  place: string;
  cells: IdentifiedCell[];
}

interface IdentifiedTable {
  place: string;
  caption?: string;
  rows: IdentifiedRow[];
}

/**
 * Extract only text and table structure; upstream nodes never enter the live DOM. Tables, rows
 * and cells keep the place they were read at: an answer of a service is shown as it arrived and
 * is replaced as a whole, never reordered, so that place names a table for as long as it is shown.
 */
const readIdentifyHtml = (text: string) => {
  const document = new DOMParser().parseFromString(text, "text/html");
  document
    .querySelectorAll(
      "script, style, template, noscript, iframe, object, embed, svg, math, form",
    )
    .forEach((node) => node.remove());
  const tables = Array.from(
    document.querySelectorAll("table"),
    (table, tablePosition): IdentifiedTable => {
      const read = `table-${tablePosition}`;
      return {
        place: read,
        caption: table.caption?.textContent?.trim(),
        rows: Array.from(table.rows, (row, rowPosition): IdentifiedRow => {
          const readRow = `${read}-row-${rowPosition}`;
          return {
            place: readRow,
            cells: Array.from(row.cells, (cell, cellPosition) => ({
              place: `${readRow}-cell-${cellPosition}`,
              text: cell.textContent?.trim() ?? "",
              header: cell.tagName === "TH",
            })),
          };
        }).filter((row) => row.cells.some((cell) => cell.text)),
      };
    },
  ).filter((table) => table.rows.length > 0);
  document.querySelectorAll("table").forEach((node) => node.remove());
  document.body
    .querySelectorAll("br, p, div, li, h1, h2, h3, h4, h5, h6")
    .forEach((node) => node.append("\n"));
  return { tables, text: document.body.textContent?.trim() ?? "" };
};

/**
 * One attribute value as text: a value which reads as a number, a boolean or a word is handed out
 * as it reads, a value which is structured is handed out as the json which arrived for it.
 */
const attributeText = (value: unknown): string => {
  if (value === null || value === undefined) return "";
  if (
    typeof value === "number" ||
    typeof value === "bigint" ||
    typeof value === "boolean"
  ) {
    return String(value);
  }
  if (typeof value === "string") return value;
  return JSON.stringify(value) ?? "";
};

/** The readable body of an html answer: its text and the tables rebuilt out of its markup. */
const HtmlIdentify = ({
  tables,
  text,
}: {
  tables: IdentifiedTable[];
  text: string;
}) => {
  const translate = useTranslate();
  if (!tables.length && !text) {
    return (
      <Typography variant="body2" color="text.secondary">
        {translate("livePreview.noFeatures")}
      </Typography>
    );
  }
  return (
    <>
      {text && (
        <Typography
          variant="body2"
          sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}
        >
          {text}
        </Typography>
      )}
      {tables.map((table) => (
        <TableContainer key={table.place} sx={{ maxHeight: 300 }}>
          <Table
            size="small"
            sx={{
              "& td, & th": {
                verticalAlign: "top",
                minWidth: 100,
                maxWidth: 280,
                overflowWrap: "anywhere",
              },
            }}
          >
            {table.caption && (
              <caption style={{ captionSide: "top" }}>{table.caption}</caption>
            )}
            <TableBody>
              {table.rows.map((row) => (
                <TableRow key={row.place}>
                  {row.cells.map((cell) => (
                    <TableCell
                      key={cell.place}
                      component={cell.header ? "th" : "td"}
                      sx={
                        cell.header
                          ? { fontWeight: "bold", bgcolor: "action.hover" }
                          : undefined
                      }
                    >
                      {cell.text}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      ))}
    </>
  );
};

/** The attributes of one feature, in two columns when the answer is paged one by one. */
const FeatureAttributes = ({
  feature,
  outlined,
}: {
  feature: unknown;
  outlined: boolean;
}) => {
  const properties = entries(
    (feature as { properties?: unknown })?.properties,
  );
  return (
    <Stack
      sx={{
        border: outlined ? 1 : 0,
        borderColor: "divider",
        p: outlined ? 1 : 0,
      }}
    >
      {(properties.length ? properties : entries(feature)).map(
        ([key, value]) => (
          <Typography
            key={key}
            component="div"
            variant="body2"
            sx={
              outlined
                ? undefined
                : {
                    display: "grid",
                    gridTemplateColumns: "minmax(90px, .8fr) minmax(0, 1.2fr)",
                    gap: 1,
                    py: 1,
                    borderTop: 1,
                    borderColor: "divider",
                    overflowWrap: "anywhere",
                  }
            }
          >
            {outlined ? (
              <>
                {key}: {attributeText(value)}
              </>
            ) : (
              <>
                <span>{key}</span>
                <span>{attributeText(value)}</span>
              </>
            )}
          </Typography>
        ),
      )}
    </Stack>
  );
};

/** The features of a json answer, one per page when the map inspector asks for that. */
const FeatureIdentify = ({
  features,
  paginate,
  page,
  onPage,
}: {
  features: IdentifiedFeature[];
  paginate: boolean;
  page: number;
  onPage: (page: number) => void;
}) => {
  const translate = useTranslate();
  if (!features.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        {translate("livePreview.noFeatures")}
      </Typography>
    );
  }
  const shown = paginate ? features.slice(page, page + 1) : features;
  return (
    <Stack spacing={1}>
      {paginate && (
        <Stack direction="row" sx={{ alignItems: "center" }} spacing={1}>
          <Typography variant="caption" sx={{ flex: 1 }}>
            {translate("viewerFeatureInfo.featurePage", {
              current: Math.min(page + 1, features.length),
              total: features.length,
            })}
          </Typography>
          <Button
            size="small"
            disabled={page === 0}
            onClick={() => onPage(page - 1)}
            aria-label={translate("ra.navigation.previous")}
          >
            ‹
          </Button>
          <Button
            size="small"
            disabled={page >= features.length - 1}
            onClick={() => onPage(page + 1)}
            aria-label={translate("ra.navigation.next")}
          >
            ›
          </Button>
        </Stack>
      )}
      {shown.map((feature) => (
        <FeatureAttributes
          key={feature.place}
          feature={feature.value}
          outlined={!paginate}
        />
      ))}
    </Stack>
  );
};

/** Presents service data as React text and tables, with the original available on demand. */
export const FeatureInfoResult = ({
  text,
  contentType,
  paginate = false,
}: {
  text: string;
  contentType: string;
  paginate?: boolean;
}) => {
  const translate = useTranslate();
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [text]);
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    const next = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [text]);
  const mediaType = contentType.split(";")[0].trim().toLowerCase();
  const html = useMemo(
    () =>
      mediaType === "text/html" || mediaType === "application/xhtml+xml"
        ? readIdentifyHtml(text)
        : undefined,
    [mediaType, text],
  );
  const parsed = useMemo(
    () =>
      mediaType === "application/json" || mediaType === "application/geo+json"
        ? parseIdentify(text)
        : undefined,
    [mediaType, text],
  );
  const features = parsed === undefined ? undefined : identifyFeatures(parsed);

  let body: ReactNode;
  if (html) {
    body = <HtmlIdentify tables={html.tables} text={html.text} />;
  } else if (features) {
    body = (
      <FeatureIdentify
        features={features}
        paginate={paginate}
        page={page}
        onPage={setPage}
      />
    );
  } else {
    body = (
      <Typography
        component="pre"
        sx={{ whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto" }}
      >
        {parsed === undefined ? text : JSON.stringify(parsed, null, 2)}
      </Typography>
    );
  }

  return (
    <Stack spacing={1} sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
      {body}
      <Accordion
        slotProps={{ transition: { unmountOnExit: true } }}
        disableGutters
        elevation={0}
        sx={{
          "&:before": { display: "none" },
          borderTop: 1,
          borderColor: "divider",
        }}
      >
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="body2">
            {translate("livePreview.rawResponse")}
          </Typography>
        </AccordionSummary>
        <AccordionDetails>
          {url && (
            <MuiLink href={url} download="getfeatureinfo.txt">
              {translate("livePreview.featureInfo")}
            </MuiLink>
          )}
          <Typography
            component="pre"
            sx={{
              fontFamily: "monospace",
              fontSize: "0.75rem",
              whiteSpace: "pre",
              maxHeight: 200,
              overflow: "auto",
            }}
          >
            {text}
          </Typography>
        </AccordionDetails>
      </Accordion>
    </Stack>
  );
};

export default FeatureInfoResult;
