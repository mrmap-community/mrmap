import { AdminContext, testDataProvider } from "react-admin";

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import FeatureInfoResult from "./FeatureInfoResult";

/** The presentation asks nothing but its text, so a key answering i18n is enough. */
const show = (props: {
  text: string;
  contentType: string;
  paginate?: boolean;
}) =>
  render(
    <AdminContext
      dataProvider={testDataProvider()}
      i18nProvider={{
        translate: (key) => key,
        changeLocale: async () => {},
        getLocale: () => "en",
      }}
    >
      <FeatureInfoResult {...props} />
    </AdminContext>,
  );

const html = (text: string, contentType = "text/html; charset=UTF-8") =>
  show({ text, contentType });

describe("identify result presentation", () => {
  it("names an identify result that holds no features", () => {
    show({
      text: '{"type":"FeatureCollection","features":[]}',
      contentType: "application/json",
    });
    expect(screen.getByText("livePreview.noFeatures")).toBeInTheDocument();
  });

  it("recognizes the empty GeoServer HTML response and keeps its source collapsed", () => {
    html(
      "<html><head><title>Geoserver GetFeatureInfo output</title><style>table.featureInfo {border:1px solid}</style></head><body>\n</body></html>",
    );
    expect(screen.getByText("livePreview.noFeatures")).toBeVisible();
    expect(screen.queryByText(/table.featureInfo/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "livePreview.rawResponse" }),
    );
    expect(screen.getByText(/table.featureInfo/)).toBeVisible();
  });

  it("rebuilds feature tables with headers, captions and decoded text while discarding active markup", () => {
    const { container } = html(`<html><head><style>body{display:none}</style></head><body>
      <script>window.stolen = localStorage.token</script><iframe src="https://untrusted.test"></iframe>
      <table onclick="alert(1)"><caption>Places</caption><tr><th>Name</th><th>Population</th></tr>
      <tr><td><a href="javascript:alert(1)">Berlin &amp; Mitte</a></td><td>123</td></tr>
      <tr><td>&lt;script&gt;literal&lt;/script&gt;</td><td><img src="missing" onerror="alert(1)">456</td></tr></table>
      </body></html>`);
    expect(screen.getByRole("table")).toHaveAccessibleName("Places");
    expect(
      screen.getByRole("columnheader", { name: "Name" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("cell", { name: "Berlin & Mitte" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("cell", { name: "<script>literal</script>" }),
    ).toBeInTheDocument();
    expect(
      container.querySelector("script, iframe, img, a, [onclick], [onerror]"),
    ).toBeNull();
    expect(screen.queryByText("livePreview.noFeatures")).toBeNull();
  });

  it("retains readable non-table HTML content including XHTML", () => {
    html(
      '<html xmlns="http://www.w3.org/1999/xhtml"><body><h2>Service message</h2><p>No matching records &amp; no errors.</p></body></html>',
      "application/xhtml+xml",
    );
    expect(screen.getByText(/Service message/)).toHaveTextContent(
      "No matching records & no errors.",
    );
    expect(screen.queryByText("livePreview.noFeatures")).toBeNull();
  });

  it("pages the features of a json answer one at a time when asked to", () => {
    show({
      text: '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"First"}},{"type":"Feature","properties":{"name":"Second"}}]}',
      contentType: "application/geo+json",
      paginate: true,
    });
    // a paginated answer shows one feature, the whole collection stays one request
    expect(screen.getByText("First")).toBeInTheDocument();
    expect(screen.queryByText("Second")).not.toBeInTheDocument();
    const next = screen.getByRole("button", { name: "ra.navigation.next" });
    expect(
      screen.getByRole("button", { name: "ra.navigation.previous" }),
    ).toBeDisabled();
    fireEvent.click(next);
    expect(screen.getByText("Second")).toBeInTheDocument();
    expect(screen.queryByText("First")).not.toBeInTheDocument();
    expect(next).toBeDisabled();
  });

  it("keeps the raw answer of a service downloadable as it arrived", () => {
    show({ text: "plain answer", contentType: "text/plain" });
    expect(screen.getByText("plain answer")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "livePreview.rawResponse" }),
    );
    // the answer is handed out for saving under the name the preview names it
    const link = screen.getByRole("link", {
      name: "livePreview.featureInfo",
    });
    expect(link).toHaveAttribute("download", "getfeatureinfo.txt");
    expect(link.getAttribute("href")).toMatch(/^blob:/);
  });
});
