import { createElement } from 'react';


export const createElementIfDefined = (elem: import("react").ComponentType | undefined) => {
  return elem === undefined ? null : createElement(elem)
}

