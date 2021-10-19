function MapContextLayerFormModel() {
  var formset = this;
  this.selectedLayer = ko.observable();
  
  // ko.when(function () {
  //     return mapContextLayerFormModel.selectedLayer() == undefined;
  // }, function (result) {  
  //     mapContextLayerFormModel.isInitialized(true);  
  // });
}

function applyFormsetBindings(formset){
  console.log(formset);
  ko.applyBindings(MapContextLayerFormModel, formset);
}


/**
 * Turns a container element into a dynamic jsTree control, binding the tree nodes to a Django
 * FormSet.
 *
 * - Each form of the form set must be inside an element of class '${formPrefix}-form'.
 * - The last form is treated as the template form for creating new forms dynamically.
 * - There must be a parent fk form field and an accompanying field '${parentField}_form_idx'.
 * - There must be a text form field for storing the node name.
 *
 * @param {string} treeContainerId - the id of the container element (must include '#')
 * @param {string} formPrefix - prefix of classes and ids of the formsets
 * @param {string} parentField - form field that contains the parent fk
 * @param {string} nameField - form field that contains the node name
 */
function initJsTreeFormset(treeContainerId, formPrefix, parentField, nameField) {
  /**
   * Replaces all Django-generated id (e.g. 'id_layer-1-name') and name attributes (e.g.
   * 'id_layer-1-name') inside the given form element.
   *
   * @param {*} el element, will be recursively adapted
   * @param {*} newFormIdx new index (zero-based)
   */
  function replaceNameAndIdAttributes(el, newFormIdx) {
    function replaceNameOrId(txt) {
      return txt.replace(RegExp(`__prefix__`, 'g'), `${newFormIdx}`);
    }
    if (el.id) {
      el.id = replaceNameOrId(el.id, newFormIdx);
    }
    if (el.getAttribute('name')) {
      el.setAttribute("name", replaceNameOrId(el.getAttribute('name'), newFormIdx));
    }
    if (el.getAttribute('for')) {
      el.setAttribute("for", replaceNameOrId(el.getAttribute('for'), newFormIdx));
    }


    Array.from(el.children).forEach(child => {
      replaceNameAndIdAttributes(child, newFormIdx);
    });
  }
  /**
   * Clones the last element of class '.${formPrefix}-form' (which is the spare form / form
   * template).
   *
   * Also fixes the ids/names of the new template element to reflect the new form id.
   *
   * @returns new number of forms (not counting the template)
   */
  function appendForm() {
    const forms = document.querySelectorAll(`.${formPrefix}-form`);  // includes all forms, also marked deletion forms
    const formNum = forms.length;
    const lastForm = forms[formNum - 1];

    // Get the element
    const emptyForm = document.querySelector(`#id_${formPrefix}_EMPTY-FORM`);

    // Create a copy of it
    var newForm = emptyForm.cloneNode(true);
    replaceNameAndIdAttributes(newForm, formNum);

    newForm.setAttribute('class', `${formPrefix}-form`);
    newForm.removeAttribute('style')
    newForm.removeAttribute('id')

    if (lastForm === undefined){
      emptyForm.after(newForm);
    } else {
      lastForm.after(newForm);
    }
    // update number of forms in management form
    // https://docs.djangoproject.com/en/3.2/topics/forms/formsets/#understanding-the-managementform
    document.querySelector(`#id_${formPrefix}-TOTAL_FORMS`).value = parseInt(document.querySelector(`#id_${formPrefix}-TOTAL_FORMS`).value) + 1;
    return formNum;
  }
  /**
   * Updates the forms to match the nodes in the jsTree instance.
   */
  function updateFormset() {
    // get the tree's nodes (in topological order, so a parent does always precede its children)
    let nodes = jsTree.get_json(undefined, {
      flat: true,
      no_a_attr: true,
      no_li_attr: true,
      no_state: true
    });

    // determine forms and their order
    const formsInOrder = [];
    const nodeIdToFormIdx = {};
    let forms = $(`.${formPrefix}-form`);
    for (i = 0; i < forms.length; i++) {
      const form = forms[i];
      if (i < nodes.length) {
        const node = nodes[i];
        const nodeForm = forms[node.data.formIdx];
        formsInOrder.push(nodeForm);
        // update form idx of node
        node.data.formIdx = i;
        jsTree.get_node(node.id).data.formIdx = i;
        nodeIdToFormIdx[node.id] = i;
      }
      form.parentElement.removeChild(form);
    }

    // re-add forms to DOM in order
    const templateForm = document.querySelector(`#id_${formPrefix}_EMPTY-FORM`);
    for (i = 0; i < formsInOrder.length; i++) {
      replaceNameAndIdAttributes(formsInOrder[i], i);
      templateForm.parentNode.insertBefore(formsInOrder[i], templateForm.nextSibling);
    }

    // update name and parent form idx
    nodes.forEach(node => {
      $(`#id_${formPrefix}-${node.data.formIdx}-${nameField}`).val(node.text);
      parentFormIdx = node.parent == '#' ? '' : nodeIdToFormIdx[node.parent];
      $(`#id_${formPrefix}-${node.data.formIdx}-${parentField}_form_idx`).val(parentFormIdx);
    });

    // update template form and management form
    //replaceNameAndIdAttributes(templateForm, formsInOrder.length);
    // update number of forms in management form
    // https://docs.djangoproject.com/en/3.2/topics/forms/formsets/#understanding-the-managementform
    document.querySelector(`#id_${formPrefix}-TOTAL_FORMS`).value = formsInOrder.length;
    // TODO instead of removing originally present forms, keep them and mark them as deleted
    document.querySelector(`#id_${formPrefix}-INITIAL_FORMS`).value = 0;
  }
  $(treeContainerId).jstree({
    "core": {
      "check_callback": function (operation, node, nodeParent, nodePosition, more) {
        // operation can be 'create_node', 'rename_node', 'delete_node', 'move_node', 'copy_node' or 'edit'
        // in case of 'rename_node' node_position is filled with the new node name
        if (operation === 'move_node') {
          return typeof nodeParent.text !== 'undefined';
        }
        return true;
      },
      "data": function (obj, cb) {
        const nodes = [];
        const forms = $(`.${formPrefix}-form`);
        if (forms.length === 0) {
          // create root node
          appendForm();
          $(`#id_${formPrefix}-0-${nameField}`).val('/');
          nodes.push({
            parent: '#',
            text: '/',
            data: {
              formIdx: 0
            }
          });
        } else {
          // form nodes have to be in topological order, so a parent does always precede its children)
          const idToFormIdx = {};
          for (i = 0; i < forms.length; i++) {
            id = $(`#id_${formPrefix}-${i}-id`).val();
            parent = $(`#id_${formPrefix}-${i}-${parentField}`).val();
            nodes.push({
              id: id,
              parent: parent || "#",
              text: $(`#id_${formPrefix}-${i}-${nameField}`).val(),
              data: {
                formIdx: i
              }
            });
            if (parent) {
              $(`#id_${formPrefix}-${i}-${parentField}_form_idx`).val(idToFormIdx[parent]);
            }
            idToFormIdx[id] = i;
          }
        }
        cb.call(this, nodes);
      }
    },
    "plugins": ["dnd", "types", "unique", "rename", "actions"],
    "dnd": {
      "copy": false,
    },
    "types": {
      "root": {
        "icon": "bi bi-folder-fill",
        "valid_children": ["default", "resource"]
      },
      "default": {
        "icon": "bi bi-folder-fill",
        "valid_children": ["default", "resource"]
      },
      "resource": {
        "icon": "bi bi-map-fill",
        "valid_children": []
      }
    }
  }).on('loaded.jstree', function() {
    const nodes = jsTree.get_json(undefined, {
      flat: true,
      no_a_attr: true,
      no_li_attr: true,
      no_state: true
    });
    $(this).jstree("open_all");
    jsTree.select_node(nodes[0].id);
  }).on('create_node.jstree', function (e, data) {
    data.node.data = {
      formIdx: appendForm()
    }
    updateFormset();
    jsTree.deselect_node(jsTree.get_selected());
    jsTree.select_node(data.node.id);
  }).on('rename_node.jstree', function (e, data) {
    updateFormset();
  }).on('delete_node.jstree', function (e, data) {
    jsTree.select_node(data.node.parent);
    updateFormset();
  }).on('move_node.jstree', function (e, data) {
    updateFormset();
  }).on('select_node.jstree', function (e, data) {
    $(`.${formPrefix}-form`).css( "display", "none" );
    $(`.${formPrefix}-form`).eq(data.node.data.formIdx).css( "display", "block" );
  });
  const jsTree = $(treeContainerId).jstree(true);
  $(treeContainerId).on('model.jstree', function (e, data) {
    data.nodes.forEach(nodeId => {
      let node = jsTree.get_node(nodeId);
      if (node.type === 'default') {
        jsTree.add_action(nodeId, {
          "id": "action_add_folder",
          "class": "bi bi-plus-circle-fill pull-right",
          "title": "Add Folder",
          "after": true,
          "selector": "a",
          "event": "click",
          "callback": function (nodeId, node, action_id, action_el) {
            jsTree.create_node(node, {}, "last", function (newNode) {
              try {
                jsTree.edit(newNode);
              } catch (ex) {
                setTimeout(function () { inst.edit(newNode); }, 0);
              }
            });
          }
        });
        if (node.parent !== '#') {
          jsTree.add_action(nodeId, {
            "id": "action_remove",
            "class": "bi bi-dash-circle-fill pull-right",
            "title": "Remove Child",
            "after": true,
            "selector": "a",
            "event": "click",
            "callback": function (nodeId, node) {
              jsTree.delete_node(node);
            }
          });
        }
        jsTree.add_action(nodeId, {
          "id": "action_edit",
          "class": "bi bi-pencil-fill pull-right",
          "title": "Edit",
          "after": true,
          "selector": "a",
          "event": "click",
          "callback": function (nodeId, node) {
            jsTree.edit(node.id);
          }
        });
      } else if (node.type === 'resource') {
        jsTree.add_action(nodeId, {
          "id": "action_remove",
          "class": "bi bi-dash-circle-fill pull-right",
          "title": "Remove",
          "after": true,
          "selector": "a",
          "event": "click",
          "callback": function (nodeId, node) {
            jsTree.delete_node(node);
          }
        });
      }
    });
  });
  return jsTree;
}
