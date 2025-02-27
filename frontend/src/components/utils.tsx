import { RaRecord } from 'react-admin';

import { TreeItem, TreeItemProps } from '@mui/x-tree-view/TreeItem';



import { ReactNode } from 'react';
import { getChildren } from './MapViewer/utils';


export const getSubTree = (nodes: RaRecord[], currentNode?: RaRecord, getTreeItemProps?: (record: RaRecord) => Partial<TreeItemProps>) => {
    const node = currentNode || nodes.find((node) => node.mpttLft === 1)
    
    const children = node && getChildren(nodes, node)
  
    const subtree: ReactNode[] = children?.map((child: RaRecord) => (
        <TreeItem 
            key={child.id} 
            itemId={child.id.toString()} 
            label={child.title}
            {...(getTreeItemProps && getTreeItemProps(child))}
        >
            {getSubTree(nodes, child)}
        </ TreeItem>
    )) || []
  
    if (currentNode === undefined && node !== undefined){
        return (
            <TreeItem 
                key={node.id} 
                itemId={node.id.toString()} 
                label={node.title} 
                {...(getTreeItemProps && getTreeItemProps(node))}
            >
                {...subtree}
            </ TreeItem>
        )
    } else {
        return subtree
    }
};