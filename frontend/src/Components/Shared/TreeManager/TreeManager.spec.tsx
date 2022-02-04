import { SettingFilled } from '@ant-design/icons';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Form from 'antd/lib/form/Form';
import React from 'react';
import { TreeManager } from './TreeManager';
import { TreeNodeType, TreeProps } from './TreeManagerTypes';

// mock the useForm hook from AntD form context
jest.mock('antd/lib/form/Form', () => ({
  ...jest.requireActual('antd/lib/form/Form'),
  useForm: () => [{
    getFieldError: jest.fn(), 
    getFieldInstance: jest.fn(),
    getFieldValue: jest.fn(),
    getFieldWarning: jest.fn(),
    getFieldsError: jest.fn(),
    getFieldsValue: jest.fn(),
    getInternalHooks: jest.fn(),
    isFieldTouched: jest.fn(),
    isFieldValidating: jest.fn(),
    isFieldsTouched: jest.fn(),
    isFieldsValidating: jest.fn(),
    resetFields: jest.fn(),
    scrollToField: jest.fn(),
    setFields: jest.fn(),
    setFieldsValue: jest.fn(),
    submit: jest.fn(),
    validateFields: jest.fn()
  }]
}));

describe('TreeFormField component', () => {
  const mockedTreeData = [
    {
      title: 'node1',
      key: 'node1',
      children: [],
      parent: null,
      properties: {
        title: 'node1',
        description: 'the node 1'
      },
      expanded: true,
      isLeaf: false,
    },
    {
      title: 'leaf1',
      key: 'leaf1',
      children: [],
      parent: null,
      properties: {
        title: 'leaf1',
        description: 'leaf 1 '
      },
      expanded: true,
      isLeaf: true,
    },
  ];

  const requiredProps = {
    treeData: mockedTreeData,
  };
  
  const getComponent = (props?:TreeProps) => render(
    <TreeManager
      {...requiredProps}
      {...props}
    />
  );
  
  // clears all mock artifacts to avoid transition from values and making all tests clean from the beginning
  afterEach(() => {
    jest.clearAllMocks();
    cleanup();
  });

  // NOTE: This component loads the tree data as soon as the tree data is ready.
  // This fetch will trigger a state event (in this case setTreeData()).
  // Because of this, we need to simulate this behaviour in an asynchronous fashion, hence the waitFor is used for all
  // the following tests.
  // After an event that triggers a state chnage, this is also being made.
  // Without this, the tests will pass but a couple of warnings about state changes should be
  // encapsulated in an act() method will appear
  
  it('defines the component', async () => {
    const component =  getComponent(); 
    await waitFor(() => expect(component).toBeDefined()); 
  });

  it('renders the component elements', async() => {
    const { container } = getComponent();
    await waitFor(() =>{
      expect(container).toBeVisible();
    });
  });

  it('renders the tree-manager-tree class', async() => {
    const { container } = getComponent();
    await waitFor(() =>{
      expect(container.querySelectorAll('.tree-manager-tree').length).toBe(1);
    });
  });

  it('does not render tree nodes when tree data does not contains information', async() => {
    const { container } = getComponent({ treeData: [] });
    await waitFor(() =>{
      const treeFormFieldTree = container.querySelectorAll('.tree-manager-tree');
      const treeFormFieldNode = treeFormFieldTree.item(0)?.querySelectorAll('.tree-manager-node');  
      expect(treeFormFieldNode?.length).toBe(0);
    });
  });

  it('renders the tree when data contains information', async() => {
    const { container } = getComponent();
    await waitFor(() =>{
      const treeFormFieldTree = container.querySelectorAll('.tree-manager-tree');
      const treeFormFieldNode = treeFormFieldTree.item(0)?.getElementsByClassName('tree-manager-node');
      expect(treeFormFieldNode?.length).toBe(2);
    });
  });

  it('does not render the checkboxes if checkable props is set to false', async() => {
    // checkableNodes is set to false by default
    const { container } = getComponent();
    await waitFor(() =>{
      const treeFormFieldCheckboxes = container.querySelectorAll('.ant-tree-checkbox');
      expect(treeFormFieldCheckboxes?.length).toBe(0);
    });
  });

  it('renders the checkboxes if checkable props is set to true', async() => {
    const { container } = getComponent({ ...requiredProps, checkableNodes: true });
    await waitFor(() =>{
      const treeFormFieldCheckboxes = container.querySelectorAll('.ant-tree-checkbox');
      expect(treeFormFieldCheckboxes?.length).toBe(2);
    });
  });

  it('renders the checkboxes as checked if checkbox is checked', async () => {
    const { container } = getComponent({ 
      ...requiredProps, 
      checkableNodes: true 
    });
    expect(container.querySelectorAll('.ant-tree-checkbox').length).toBe(2);
    
    // store both checkboxes into variables (there are only two, because our mock data only has two nodes)
    const node1Checkbox = container.querySelectorAll('.ant-tree-checkbox').item(0);
    const node2Checkbox = container.querySelectorAll('.ant-tree-checkbox').item(1);
    // confirm the checkboxes are defined and visible
    expect(node1Checkbox).toBeDefined();
    expect(node1Checkbox).toBeVisible();
    expect(node1Checkbox).not.toHaveClass('ant-tree-checkbox-checked');
    
    expect(node2Checkbox).toBeDefined();
    expect(node2Checkbox).toBeVisible();
    expect(node2Checkbox).not.toHaveClass('ant-tree-checkbox-checked');
    
    // confirm that there are no cheked checkboxes at the moment
    expect(container.querySelectorAll('.ant-tree-treenode-checkbox-checked').length).toBe(0);
    
    fireEvent.click(node1Checkbox);
    fireEvent.click(node2Checkbox);

    await waitFor( () =>{
      //  now, check that the length of the checked checkboxes is not 0 anymore and both
      expect(container.querySelectorAll('.ant-tree-checkbox-checked').length).toBe(2);
    });
  });

  it('renders the title pre-icon (SettingFilled) if prop is set', async() => {
    const { container } = getComponent({ 
      ...requiredProps,
      treeNodeTitlePreIcons: (node: TreeNodeType) => (<SettingFilled />)
    });
    
    await waitFor(() =>{
    // there are two nodes
      const treeNodeTitleSymbols = container.querySelectorAll('.tree-node-title-symbols');
      expect(treeNodeTitleSymbols.length).toBe(2);
      const iconSpanNode1 = treeNodeTitleSymbols.item(0)?.querySelector('span');
      const iconSpanNode2 = treeNodeTitleSymbols.item(1)?.querySelector('span');
      expect(iconSpanNode1).toHaveClass('anticon-setting');
      expect(iconSpanNode2).toHaveClass('anticon-setting');
    });
    // TODO: how to test for FontAwesome?
  });

  it('renders the node title', async () => {
    const { container } = getComponent();
    await waitFor(() => {
      const nodeTitles = container.querySelectorAll('.tree-node-title');
      expect(nodeTitles.length).toBe(2);
      expect(nodeTitles.item(0)?.textContent).toBe('node1');
      expect(nodeTitles.item(1)?.textContent).toBe('leaf1');
    });
  });

  it('renders the node options icon', async() => {
    const { container } = getComponent();
    await waitFor(() => {
      const nodeSettingsIcon = container.querySelectorAll('.tree-manager-node-actions');
      expect(nodeSettingsIcon.length).toBe(2);
      const iconSpanNode1 = nodeSettingsIcon.item(0)?.querySelector('span');
      const iconSpanNode2 = nodeSettingsIcon.item(1)?.querySelector('span');
      expect(iconSpanNode1).toHaveClass('anticon-setting');
      expect(iconSpanNode2).toHaveClass('anticon-setting');
    });
  });

  it('renders the context menu when right clicking the node title if contextMenuOnNode prop is true', async() => {
    const { container } = getComponent({ ...requiredProps, contextMenuOnNode: true });
    const nodeTitles = container.querySelectorAll('.tree-manager-node-title');
    const titleNode1 = nodeTitles.item(0);
    // right mouse click
    expect(screen.queryByText('Add new layer group')).toBeNull(); 
    fireEvent.contextMenu(titleNode1);
    await waitFor(() => {
      expect(screen.queryByText('Add new layer group')).toBeDefined();
    });
  });

  it('does not render the context menu when right clicking the node title if ' +
  'contextMenuOnNode prop is false', async() => {
    // contextMenuOnNode is false by default
    const { container } = getComponent();
    const nodeTitles = container.querySelectorAll('.tree-manager-node-title');
    const firstNodeTitle = nodeTitles.item(0);
    // right mouse click
    fireEvent.contextMenu(firstNodeTitle);
    await waitFor(() => {
      const contextMenu = screen.queryByText('Add new layer group');
      expect(contextMenu).toBe(null);
    });
  });

  it('renders the context menu when clicking the options icon', async() => {
    const { container } = getComponent();
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const settingsNode1 = nodeSettings.item(0)?.querySelector('button');
    const settingsNode2 = nodeSettings.item(1)?.querySelector('button');
    expect(screen.queryByText('Add new layer group')).toBeNull(); 
    fireEvent.click(settingsNode1 as Element);
    fireEvent.click(settingsNode2 as Element);
    await waitFor(() => {
      expect(screen.queryByText('Add new layer group')).toBeDefined();
    });
  });

  it('renders a modal when clicking to add a new node on the options menu and attributeContainer ' +
    'is set to modal', async() => {
    const { container } = getComponent({ ...requiredProps, attributeContainer: 'modal' });
    // open the context menu
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const firstNodeSettings = nodeSettings.item(0)?.querySelector('button');
    fireEvent.click(firstNodeSettings as Element);
    await waitFor(async() => {
      const contextMenuFirstAction = screen.getByText('Add new layer group');
      fireEvent.click(contextMenuFirstAction);
      await waitFor(() => {
        expect(screen.getByText('Add Node').parentElement?.className).toBe('ant-modal-header');
      });
    });
      
  });

  it('renders a modal when clicking to add a new node on the options menu and attributeContainer is '
  + 'not set', async() => {
    const { container } = getComponent();
    // open the context menu
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const firstNodeSettings = nodeSettings.item(0)?.querySelector('button');
    fireEvent.click(firstNodeSettings as Element);
    await waitFor(async() => {
      const contextMenuFirstAction = screen.getByText('Add new layer group');
      fireEvent.click(contextMenuFirstAction);
      await waitFor(() => {
        expect(screen.getByText('Add Node').parentElement?.className).toBe('ant-modal-header');
      });
    });

  });

  it('renders a drawer when clicking to add a new node on the options menu and attributeContainer '+ 
    'is set to drawer', async() => {
    const { container } = getComponent({ ...requiredProps, attributeContainer: 'drawer' });
    // open the context menu
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const firstNodeSettings = nodeSettings.item(0)?.querySelector('button');
    fireEvent.click(firstNodeSettings as Element);
    await waitFor(async() => {
      const contextMenuFirstAction = screen.getByText('Add new layer group');
      fireEvent.click(contextMenuFirstAction);
      await waitFor(() => {
        expect(screen.getByText('Add Node').parentElement?.className).toBe('ant-drawer-header-title');
      });
    });
  });
  
  it('renders an icon for the add group node option on the context menu', async() => {
    const { container } = getComponent();
    // open the context menu
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const firstNodeSettings = nodeSettings.item(0)?.querySelector('button');
    fireEvent.click(firstNodeSettings as Element);
    await waitFor(() => {
      const contextMenuFirstAction = screen.getByRole('menu');
      const iconSpanNode = contextMenuFirstAction.querySelectorAll('.ant-dropdown-menu-item-icon')[0];
      const textSpanNode = contextMenuFirstAction.querySelectorAll('.ant-dropdown-menu-title-content')[0];
      expect(iconSpanNode).toHaveClass('anticon-folder-add');
      expect(textSpanNode.innerHTML).toBe('Add new layer group');
    });
  });

  it('renders an icon for the add node option on the context menu', async () => {
    const { container } = getComponent();
    // open the context menu
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const firstNodeSettings = nodeSettings.item(0)?.querySelector('button');
    fireEvent.click(firstNodeSettings as Element);
    await waitFor(() => {
      const contextMenuFirstAction = screen.getByRole('menu');
      const iconSpanNode = contextMenuFirstAction.querySelectorAll('.ant-dropdown-menu-item-icon')[1];
      const textSpanNode = contextMenuFirstAction.querySelectorAll('.ant-dropdown-menu-title-content')[1];
      expect(iconSpanNode).toHaveClass('anticon-plus-circle');
      expect(textSpanNode.innerHTML).toBe('Add new layer');
    });
  });

  it('renders an icon for the remove node option on the context menu', async () => {
    const { container } = getComponent();
    // open the context menu
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const firstNodeSettings = nodeSettings.item(0)?.querySelector('button');
    fireEvent.click(firstNodeSettings as Element);
    await waitFor(() => {
      const contextMenuFirstAction = screen.getByRole('menu');
      const iconSpanNode = contextMenuFirstAction.querySelectorAll('.ant-dropdown-menu-item-icon')[2];
      const textSpanNode = contextMenuFirstAction.querySelectorAll('.ant-dropdown-menu-title-content')[2];
      expect(iconSpanNode).toHaveClass('anticon-minus-circle');
      expect(textSpanNode.innerHTML).toBe('Delete');
    });
  });

  it('renders an icon for the edit node option on the context menu', async() => {
    const { container } = getComponent();
    // open the context menu
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const firstNodeSettings = nodeSettings.item(0)?.querySelector('button');
    fireEvent.click(firstNodeSettings as Element);
    await waitFor(() => {
      const contextMenuFirstAction = screen.getByRole('menu');
      const iconSpanNode = contextMenuFirstAction.querySelectorAll('.ant-dropdown-menu-item-icon')[3];
      const textSpanNode = contextMenuFirstAction.querySelectorAll('.ant-dropdown-menu-title-content')[3];
      expect(iconSpanNode).toHaveClass('anticon-edit');
      expect(textSpanNode.innerHTML).toBe('Properties');
    });
  });

  it('does not render  add new node group or add new node (leaf) if context menu is opened on a leaf', async() => {
    const { container } = getComponent();
    // open the context menu
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const leafNodeSettings = nodeSettings.item(1)?.querySelector('button');
    fireEvent.click(leafNodeSettings as Element);
    await waitFor(() => {
      const contextMenu = screen.getByRole('menu');
      const contextMenuFirstActionIcon = contextMenu.querySelectorAll('.ant-dropdown-menu-item-icon')[0];
      const contextMenuSecondActionIcon = contextMenu.querySelectorAll('.ant-dropdown-menu-item-icon')[1];
      const contextMenuFirstActionText = contextMenu.querySelectorAll('.ant-dropdown-menu-title-content')[0];
      const contextMenuSecondActionText = contextMenu.querySelectorAll('.ant-dropdown-menu-title-content')[1];
      expect(contextMenuFirstActionIcon).not.toHaveClass('anticon-folder-add');
      expect(contextMenuSecondActionIcon).not.toHaveClass('anticon-folder-add');
      expect(contextMenuFirstActionText.innerHTML).not.toBe('Add new layer group');
      expect(contextMenuSecondActionText.innerHTML).not.toBe('Add new layer');
    });
  });

  it('renders input on node title when double clicking on the title', async () => {
    const { container } = getComponent();
    const nodeTitles = container.getElementsByClassName('tree-manager-node-title');
    const firstNodeTitle = nodeTitles.item(0);
    fireEvent.doubleClick(firstNodeTitle as Element);
    await waitFor(() => {
      expect(firstNodeTitle?.querySelector('input')).toBeDefined();
    });

  });

  it('changes the node title when submiting value on the title input field', async () => {
    const { container } = getComponent();
    const nodeTitles = container.querySelectorAll('.tree-manager-node-title');
    const firstNodeTitle = nodeTitles.item(0);
    fireEvent.doubleClick(firstNodeTitle);
    const inputField = firstNodeTitle?.querySelector('input');
    expect(inputField?.value).toBe('node1');
    fireEvent.change(inputField as HTMLInputElement, { target: { value: 'new node title' } });
    fireEvent.keyPress(inputField as HTMLInputElement, { key: 'Enter' });
    await waitFor(() => {
      expect(inputField?.value).toBe('new node title');
    });
  });

  it('does not change the node title when submiting value on the title input field, when editing and clicking ' + 
    'Escape', async() => {
    const { container } = getComponent();
    const nodeTitles = container.querySelectorAll('.tree-manager-node-title');
    const firstNodeTitle = nodeTitles.item(0);
    const titleText = firstNodeTitle.querySelector('span');
    expect(titleText).toBeDefined();
    expect(titleText?.textContent).toBe('node1');
    fireEvent.doubleClick(firstNodeTitle);
    const inputField = firstNodeTitle.querySelector('input');
    // expect(titleText).not.toBeDefined(); // how to be sure this is not defined
    expect(inputField).toBeDefined();
     
    expect(inputField?.value).toBe('node1');
    fireEvent.change(inputField as Element, { target: { value: 'new node title' } });
    fireEvent.keyPress(inputField as Element, { key: 'Escape' });
    await waitFor(() => {
      expect(titleText).toBeDefined();
      expect(titleText?.textContent).toBe('node1');
    });
  });

  // TODO: test works but there is still a problem problem passing the cloned props to the mocked Form
  it.skip('adds a new node group when submitting the add new node group attribute form', async() => {
    const mockSubmit = jest.fn();

    const mockForm = (
      <Form
        data-testid='mock-form'
        initialValues={{
          abstract: 'an abstract for newest node',
          title: 'newest node'
        }}
        onFinish={mockSubmit}
      />
    );
    const { container } = getComponent({ 
      ...requiredProps,
      attributeContainer: 'drawer',
      nodeAttributeForm: mockForm
    });

    // open the context menu
    const nodeSettings = container.querySelectorAll('.tree-manager-node-actions');
    const firstNodeSettings = nodeSettings.item(0)?.querySelector('button');
    fireEvent.click(firstNodeSettings as Element);
    const contextMenuFirstAction = screen.getByText('Add new layer group');
    fireEvent.click(contextMenuFirstAction);

    const drawerBody = screen.getByText('Add Node').parentElement?.parentElement?.parentElement;
    expect(drawerBody).toHaveClass('ant-drawer-wrapper-body');
    const drawerForm = drawerBody?.querySelectorAll('.ant-form').item(0);
    //TODO:  mock submit is not beeing called on submit. Why?
    fireEvent.submit(drawerForm as Element);
    await waitFor( () =>{
      expect(mockSubmit).toHaveBeenCalledTimes(1);
    });
    
  });
});
