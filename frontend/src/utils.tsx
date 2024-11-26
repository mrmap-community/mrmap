import { createElement } from 'react';


export const createElementIfDefined = (elem: any) => {
  return elem === undefined ? <div></div> : createElement(elem)
}

