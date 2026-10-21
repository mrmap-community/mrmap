import { ReactNode } from 'react';

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { OWSContext, OWSResource } from '../../../ows-lib/OwsContext/core';
import { OWSContextDocument } from '../../../ows-lib/OwsContext/utils';
import { OwsContextBase, useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';
import EditOwsContextDialog from './EditOwsContextDialog';

// monaco is loaded from a cdn, the editor is reduced to what the dialog uses
vi.mock('@monaco-editor/react', () => ({
  Editor: ({ value, onChange }: { value: string, onChange?: (value?: string) => void }) => (
    <textarea
      data-testid="editor"
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
    />
  )
}));

const initialFeature = new OWSResource({
  title: 'Karte RP',
  updated: '2024-05-03T10:26:38.476Z',
  folder: '/0'
});

const ContextTitles = () => {
  const { owsContext } = useOwsContextBase();

  return (
    <div>
      {owsContext.features.map(feature =>
        <div key={String(feature.id)} data-testid="feature-title">{feature.properties.title}</div>
      )}
    </div>
  );
};

const renderDialog = (): ((open: boolean) => void) => {
  const setOpen = vi.fn();

  const wrapper = ({ children }: { children: ReactNode }) => (
    <OwsContextBase initialFeatures={[initialFeature]}>
      <ContextTitles />
      {children}
    </OwsContextBase>
  );

  render(<EditOwsContextDialog open setOpen={setOpen} />, { wrapper });

  return setOpen;
};

const documentWith = (title: string) => {
  const document = OWSContextDocument('https://www.example.org/context/1/');
  document.features = [{
    type: 'Feature',
    properties: { title: title, updated: '2024-05-03T10:26:38.476Z', folder: '/0' }
  }];
  return document;
};

const writeDocument = (value: string) => {
  fireEvent.change(screen.getByTestId('editor'), { target: { value: value } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
};

describe('EditOwsContextDialog', () => {

  it('keeps the dialog open on invalid json and reports it', () => {
    const setOpen = renderDialog();

    writeDocument('{ "type": "FeatureCollection"');

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(setOpen).not.toHaveBeenCalled();
    expect(screen.getByTestId('ows-context-error')).toHaveTextContent('Invalid JSON');
    expect(screen.getByTestId('feature-title')).toHaveTextContent('Karte RP');
  });

  it('reports the offending field and keeps the previous context', () => {
    const setOpen = renderDialog();
    const document = documentWith('Neu');
    delete (document.properties as Record<string, unknown>).title;

    writeDocument(JSON.stringify(document));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(setOpen).not.toHaveBeenCalled();
    expect(screen.getByTestId('ows-context-error')).toHaveTextContent('properties.title');
    expect(screen.getByTestId('feature-title')).toHaveTextContent('Karte RP');
  });

  it('reports unsupported offerings as warnings but applies the document', async () => {
    const setOpen = renderDialog();
    const document = documentWith('Neu');
    document.features[0].properties.offerings = [{
      code: 'http://www.opengis.net/spec/owc/1.0/req/wfs',
      operations: [{ code: 'GetFeatureInfo', method: 'GET', href: 'https://www.example.org/wfs' }]
    }];

    writeDocument(JSON.stringify(document));

    expect(screen.getByTestId('ows-context-warning'))
      .toHaveTextContent('the viewer cannot render');
    expect(setOpen).toHaveBeenCalledWith(false);
    expect(await screen.findByTestId('feature-title')).toHaveTextContent('Neu');
  });

  it('applies a valid document and closes the dialog', async () => {
    const setOpen = renderDialog();

    writeDocument(JSON.stringify(documentWith('Neu')));

    expect(screen.queryByTestId('ows-context-error')).not.toBeInTheDocument();
    expect(setOpen).toHaveBeenCalledWith(false);
    expect(await screen.findByTestId('feature-title')).toHaveTextContent('Neu');
  });
});


it('keeps copyable JSON redacted and preserves session credentials when saving a local edit', () => {
  let current: ReturnType<typeof useOwsContextBase>;
  const Tester = () => {
    current = useOwsContextBase();
    return <button onClick={() => {
      const next = OWSContext.fromPlainObject(current.owsContext);
      next.authenticationHeaders = [{ id: 'secret', type: 'header', name: 'Authorization', value: 'Basic password', origin: 'https://protected.example' }];
      current.setOwsContext(next);
    }}>configure</button>;
  };
  render(<OwsContextBase><Tester /><EditOwsContextDialog open setOpen={vi.fn()} /></OwsContextBase>);
  fireEvent.click(screen.getByRole('button', { name: 'configure', hidden: true }));
  const document = (screen.getByTestId('editor') as HTMLTextAreaElement).value;
  expect(document).not.toContain('Basic password');
  expect(JSON.parse(document).authenticationHeaders[0].value).toBe('');
  const edited = JSON.parse(document);
  edited.properties.title = 'Edited locally';
  writeDocument(JSON.stringify(edited));
  expect(current!.owsContext.properties.title).toBe('Edited locally');
  expect(current!.owsContext.authenticationHeaders![0].value).toBe('Basic password');
});
