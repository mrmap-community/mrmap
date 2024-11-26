import { ReactNode } from 'react';

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { OWSResource } from '../../ows-lib/OwsContext/core';
import { karteRpFeatures as testdata } from '../../ows-lib/OwsContext/tests/data';
import { treeify } from '../../ows-lib/OwsContext/utils';
import { OwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase';
import NodeCheckbox from './NodeCheckbox';


const getKarteRpFeatures = () => {
  const karteRp = testdata.map(resource => new OWSResource(resource.properties, resource.id, resource.bbox, resource.geometry));
  // Land 3 active
  karteRp[5].properties.active = true
  // Wald, Wald 0, Wald 1, Wald 2, Wald 3, Wald 4 active
  karteRp[6].properties.active = true
  karteRp[7].properties.active = true
  karteRp[8].properties.active = true
  karteRp[9].properties.active = true
  karteRp[10].properties.active = true
  karteRp[11].properties.active = true
  return karteRp
}

const karteRp = getKarteRpFeatures()

const MapViewerBaseWrapper = ({ children }: { children: ReactNode }) => {
  return (
    <OwsContextBase initialFeatures={karteRp}>
      {children}
    </OwsContextBase>
  )
}

describe('LayerTree', () => {
  
  it('NodeCheckbox check active states on wald', () => {
    const tree = treeify(karteRp)

    render(<NodeCheckbox node={tree[0].children[1]}/>, {wrapper: MapViewerBaseWrapper});

    expect(screen.getByRole('checkbox')).toHaveProperty('dataset.indeterminate', 'false');
    expect(screen.getByRole('checkbox')).toHaveProperty('checked', true);

  });

  it('NodeCheckbox check active states on Landesfläche', () => {
    const tree = treeify(karteRp)

    render(<NodeCheckbox node={tree[0].children[0]}/>, {wrapper: MapViewerBaseWrapper});

    expect(screen.getByRole('checkbox')).toHaveProperty('dataset.indeterminate', 'true');
    expect(screen.getByRole('checkbox')).toHaveProperty('checked', false);

  });
});