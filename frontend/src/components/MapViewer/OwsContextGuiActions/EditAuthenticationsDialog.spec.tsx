import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OWSContext, OWSResource } from "../../../ows-lib/OwsContext/core";
import EditAuthenticationsDialog from "./EditAuthenticationsDialog";

// the editor renders many selects and needs more than the default timeout
vi.setConfig({ testTimeout: 20000 });

const state = vi.hoisted(() => ({
  context: undefined as OWSContext | undefined,
  update: vi.fn(),
}));
vi.mock("react-admin", () => ({
  useTranslate: () => (key: string) => key.split(".").pop(),
}));
vi.mock("../../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  useOwsContextBase: () => ({
    owsContext: state.context,
    updateOwsContext: state.update,
  }),
}));
beforeEach(() => {
  state.context = new OWSContext(undefined, [
    new OWSResource({
      title: "Layer",
      updated: new Date().toISOString(),
      folder: "/0",
      offerings: [
        {
          code: "http://www.opengis.net/spec/owc-geojson/1.0/req/wms",
          operations: [
            {
              code: "GetMap",
              method: "GET",
              href: "https://example.com/wms",
              active: true,
            },
            {
              code: "GetFeatureInfo",
              method: "GET",
              href: "https://example.com/wms",
              active: false,
            },
          ],
        },
      ],
    }),
  ]);
  state.update.mockClear();
});
const add = () => {
  fireEvent.change(screen.getByLabelText("origin"), {
    target: { value: "https://example.com/wms" },
  });
  fireEvent.change(screen.getByLabelText("newSecret"), {
    target: { value: "Basic test-password" },
  });
  fireEvent.click(screen.getByRole("button", { name: "add" }));
};
const select = (label: RegExp, option: RegExp) => {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: label }));
  fireEvent.click(screen.getByRole("option", { name: option }));
};
describe("authentication editor", () => {
  it("creates, assigns and removes credentials independently of operation activation", () => {
    render(<EditAuthenticationsDialog open setOpen={vi.fn()} />);
    add();
    select(/GetMap/, /example.com/);
    select(/GetFeatureInfo/, /example.com/);
    select(/GetMap/, /none/);
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    const saved: OWSContext = state.update.mock.calls[0][0];
    expect(saved).toBeInstanceOf(OWSContext);
    expect(saved.authenticationHeaders).toEqual([
      expect.objectContaining({
        origin: "https://example.com",
        name: "Authorization",
        value: "Basic test-password",
      }),
    ]);
    const operations = saved.features[0].getWmsOffering()!.operations!;
    expect(operations[0]["x-authentication-id"]).toBeUndefined();
    expect(operations[1]["x-authentication-id"]).toBe(
      saved.authenticationHeaders![0].id,
    );
    expect(operations.map((operation) => operation.active)).toEqual([
      true,
      false,
    ]);
    expect(state.context?.authenticationHeaders).toBeUndefined();
  });
  it("keeps missing assignments visible when a credential is deleted", () => {
    render(<EditAuthenticationsDialog open setOpen={vi.fn()} />);
    add();
    select(/GetMap/, /example.com/);
    fireEvent.click(screen.getByRole("button", { name: "delete" }));
    expect(screen.getAllByText("missing").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "save" }));
    expect(state.update.mock.calls[0][0].authenticationHeaders).toEqual([]);
  });
  it("discards unsaved additions when reopened", () => {
    const { rerender } = render(
      <EditAuthenticationsDialog open setOpen={vi.fn()} />,
    );
    add();
    rerender(<EditAuthenticationsDialog open={false} setOpen={vi.fn()} />);
    rerender(<EditAuthenticationsDialog open setOpen={vi.fn()} />);
    expect(screen.queryByLabelText("secret")).not.toBeInTheDocument();
    expect(state.update).not.toHaveBeenCalled();
  });
});

it('creates Basic credentials for an explicitly configured operation origin', () => {
  render(<EditAuthenticationsDialog open setOpen={vi.fn()} />);
  fireEvent.change(screen.getByLabelText('origin'), { target: { value: 'https://example.com' } });
  select(/method/, /Basic/);
  fireEvent.change(screen.getByLabelText('username'), { target: { value: 'reader' } });
  fireEvent.change(screen.getByLabelText('password'), { target: { value: 'secret' } });
  fireEvent.click(screen.getByRole('button', { name: 'add' }));
  select(/GetFeatureInfo/, /example.com/);
  fireEvent.click(screen.getByRole('button', { name: 'save' }));
  expect(state.update.mock.calls[0][0].authenticationHeaders).toEqual([expect.objectContaining({ name: 'Authorization', origin: 'https://example.com', value: `Basic ${btoa('reader:secret')}` })]);
});
