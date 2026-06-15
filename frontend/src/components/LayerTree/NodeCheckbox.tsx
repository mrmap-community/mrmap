import { MouseEvent, useCallback, useMemo, type ReactNode } from 'react'

import { Checkbox } from '@mui/material'

import { TreeifiedOWSResource } from '../../ows-lib/OwsContext/types'
import { useOwsContextBase } from '../../react-ows-lib/ContextProvider/OwsContextBase'

export interface TreeNodeCheckboxProps {
  node: TreeifiedOWSResource
}

const TreeNodeCheckbox = ({ 
  node 
}: TreeNodeCheckboxProps): ReactNode => {
  const { owsContext, setFeatureActive } = useOwsContextBase()

  const feature = useMemo(()=>{
    return owsContext.findResourceByFolder(node.properties.folder ?? '')
  },[node])

  const checked = useMemo(()=>(feature?.properties.active ?? false), [feature])

  const onClick = useCallback((event: MouseEvent) => {
        event.preventDefault()
        event.stopPropagation()
        console.log('huhu')
        if (feature === undefined) return
        setFeatureActive(feature.properties.folder ?? '', !!checked)
  }, [feature, setFeatureActive])

  const isIndeterminate = useMemo(() => {
    if (feature === undefined) return false
    return !feature.properties.active && owsContext.getIndeterminateStateOf(feature)
  }, [owsContext, feature])

  return (
    <Checkbox
      key={`checkbox-node-${feature?.properties.folder}`}
      id={`checkbox-node-${feature?.properties.folder}`}
      checked={checked}
      indeterminate={isIndeterminate}
      tabIndex={-1}
      onClick={onClick}
    />
  )
}

export default TreeNodeCheckbox
