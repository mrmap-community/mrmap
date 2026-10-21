import { createElement, Fragment } from 'react';


export const createElementIfDefined = (elem: import("react").ComponentType | undefined) => {
  return elem === undefined ? <Fragment></Fragment> : createElement(elem)
}

