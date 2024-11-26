import { MouseEvent, useCallback, useMemo, type ChangeEvent, type ReactNode } from 'react'

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

  const handleChange = useCallback((event: ChangeEvent | MouseEvent, checked?: boolean) => {
    event.stopPropagation()
    if (feature === undefined) return
    setFeatureActive(feature, (checked ?? !feature.properties.active) || true)
  }, [feature, setFeatureActive])


  const isIndeterminate = useMemo(() => {
    if (feature === undefined) return false
    return !feature.properties.active && owsContext.getIndeterminateStateOf(feature)
  }, [owsContext, feature])

  return (
    <Checkbox
      key={`checkbox-node-${feature?.properties.folder}`}
      id={`checkbox-node-${feature?.properties.folder}`}
      checked={feature?.properties.active ?? false}
      indeterminate={isIndeterminate}
      tabIndex={-1}
      onChange={handleChange}
      onClick={handleChange}
    />
  )
}

export default TreeNodeCheckbox
