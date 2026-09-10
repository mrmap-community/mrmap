import { createElement, Fragment } from 'react';


export const createElementIfDefined = (elem: any) => {
  return elem === undefined ? <Fragment></Fragment> : createElement(elem)
}

