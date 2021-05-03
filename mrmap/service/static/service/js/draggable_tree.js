$(function () {
  function get_node_by_id(node_id) {
    return $('#mapcontext_tree').jstree(true).get_node(node_id);
  }
  function get_base_url(node_id) {
    let mapContextId = $('#mapcontext_tree').data("mapcontext-id");
    return '/resource/mapcontext/' + mapContextId + '/folders';
  }
  function get_node_name(node) {
    let name = node.text.trim();
    if (name !== '/') {
      return name;
    }
    return '';
  }
  function get_folder_path(node) {
    let path = '';
    while (node.parent && node.parent !== '#') {
      node = get_node_by_id(node.parent);
      path = get_node_name(node) + "/" + path;
    }
    return path;
  }
  function url_encode_folder_path(path) {
    console.log(path + " -> " + path.split('/').map(component => encodeURIComponent(component)).join('/'));
    return path.split('/').map(component => encodeURIComponent(component)).join('/');
  }
  function update_layer_tree_input() {
    let tree = $('#mapcontext_tree').jstree(true);
    let tree_state = tree.get_json(undefined, {
      flat: true,
      no_a_attr: true,
      no_li_attr: true,
      no_state: true
    }).map(node => ({
      id: node.id,
      text: node.text,
      type: node.type,
      parent: node.parent,
      data: node.data
    }));
    $('#id_mapcontext_form input[name="layer_tree"]').val(JSON.stringify(tree_state));
  }
  $('#mapcontext_tree').jstree({
    "core": {
      "check_callback": function (operation, node, node_parent, node_position, more) {
        // operation can be 'create_node', 'rename_node', 'delete_node', 'move_node', 'copy_node' or 'edit'
        // in case of 'rename_node' node_position is filled with the new node name
        if (operation === 'move_node') {
          return typeof node_parent.text !== 'undefined';
        }
        return true;
      },
      "data": function (obj, cb) {
        let data = $('#id_mapcontext_form input[name="layer_tree"]').val();
        if (!data) {
          data = '[ "/" ]';
          $('#id_mapcontext_form input[name="layer_tree"]').val(data);
        }
        console.log("data", data);
        data = JSON.parse(data);
        cb.call(this, data);
      }
    },
    "plugins": ["dnd", "types", "unique", "rename", "actions"],
    "dnd": {
      "copy": false,
    },
    "types": {
      "root": {
        "icon": "fas fa-folder",
        "valid_children": ["default", "resource"]
      },
      "default": {
        "icon": "fas fa-folder",
        "valid_children": ["default", "resource"]
      },
      "resource": {
        "icon": "fas fa-map",
        "valid_children": []
      }
    }
  }).on('create_node.jstree', function (e, data) {
    update_layer_tree_input();
    //        let folderPath = get_folder_path(data.node);
    //        let bodyData = {
    //          name : data.node.text
    //        }
    //        $.ajax({
    //          type: 'POST',
    //          url: get_base_url() + url_encode_folder_path(folderPath),
    //          contentType: 'application/json',
    //          data: JSON.stringify(bodyData),
    //        }).done(function () {
    //          // TODO id?
    //          data.instance.set_id(data.node, Date.now());
    //        }).fail(function () {
    //          data.instance.refresh();
    //        });
  }).on('rename_node.jstree', function (e, data) {
    update_layer_tree_input();
    //        let folderPath = get_folder_path(data.node) + data.old;
    //        let bodyData = {
    //          name : data.text
    //        }
    //        $.ajax({
    //          type: 'PUT',
    //          url: get_base_url() + url_encode_folder_path(folderPath),
    //          contentType: 'application/json',
    //          data: JSON.stringify(bodyData),
    //        }).fail(function () {
    //          data.instance.refresh();
    //        });
  }).on('delete_node.jstree', function (e, data) {
    update_layer_tree_input();
    //        let folderPath = get_folder_path(data.node) + data.node.text;
    //        $.ajax({
    //          type: 'DELETE',
    //          url: get_base_url() + url_encode_folder_path(folderPath)
    //        }).fail(function () {
    //          data.instance.refresh();
    //        })
  });
  $('#mapcontext_tree').on('move_node.jstree', function (e, data) {
    update_layer_tree_input();
    //      let path = data.node.text;
    //      let oldParent = get_node_by_id(data.old_parent);
    //      path = get_folder_path(oldParent) + get_node_name(oldParent) + '/' + path;
    //
    //      let target = get_folder_path(data.node);
    //      // position = 0 -> use parent as reference and use 'first-child'
    //      let position = 'first-child';
    //      if (data.position > 0) {
    //        // position > 0 -> use my left sibling as reference and use 'right'
    //        let parent = get_node_by_id(data.parent);
    //        left_sibling = get_node_by_id(parent.children[data.position - 1]);
    //        target = target + get_node_name(left_sibling);
    //        position = 'right'
    //        console.log ('first-child: ' + target);
    //      }
    //      console.log ('move to ' + target + " (" + position + ")");
    //      let bodyData = {
    //        target : target,
    //        position : position
    //      }
    //      $.ajax({
    //        type: 'PUT',
    //        url: get_base_url() + url_encode_folder_path(path),
    //        contentType: 'application/json',
    //        data: JSON.stringify(bodyData),
    //      }).fail(function () {
    //        data.instance.refresh();
    //      });
  });
  //    $('#id_modal_wmsresource').on('hidden.bs.modal', function() {
  //        $( '#id_modal_' ).modal( 'show' );
  //    });
  let layerTree = $('#mapcontext_tree').jstree(true);
  $('#mapcontext_tree').on('model.jstree', function (e, data) {
    data.nodes.forEach(node_id => {
      let node = layerTree.get_node(node_id);
      if (node.type === 'default') {
        layerTree.add_action(node_id, {
          "id": "action_add_layer",
          "class": "fas fa-map pull-right",
          "title": "Add WMS Layer",
          "after": true,
          "selector": "a",
          "event": "click",
          "callback": function (node_id, node, action_id, action_el) {
            $('#id_modal_owsresource').modal('show');
            $('#id_modal_owsresource form').off('submit');
            $('#id_modal_owsresource form').on('submit', function (event) {
              let jstree = $('#mapcontext_tree').jstree(true);
              let data = $('#id_modal_owsresource').find('select[name="layer"]').select2('data')[0];
              let childNode = {
                text: $('#id_modal_owsresource').find('input[name="name"]').val(),
                type: "resource",
                data: {
                  wms_layer: {
                    id: data.id,
                    text: data.text
                  }
                }
              };
              jstree.create_node(node, childNode, "last", function (new_node) {
                $('#id_modal_owsresource').modal('hide');
              });
              event.preventDefault();
            });
          }
        });
        layerTree.add_action(node_id, {
          "id": "action_add_folder",
          "class": "fas fa-plus-circle pull-right",
          "title": "Add Folder",
          "after": true,
          "selector": "a",
          "event": "click",
          "callback": function (node_id, node, action_id, action_el) {
            let jstree = $('#mapcontext_tree').jstree(true);
            jstree.create_node(node, {}, "last", function (new_node) {
              try {
                jstree.edit(new_node);
              } catch (ex) {
                setTimeout(function () { inst.edit(new_node); }, 0);
              }
            });
          }
        });
        if (node.parent !== '#') {
          layerTree.add_action(node_id, {
            "id": "action_remove",
            "class": "fas fa-minus-circle pull-right",
            "title": "Remove Child",
            "after": true,
            "selector": "a",
            "event": "click",
            "callback": function (node_id, node, action_id, action_el) {
              let jstree = $('#mapcontext_tree').jstree(true);
              jstree.delete_node(node);
            }
          });
        }
        layerTree.add_action(node_id, {
          "id": "action_edit",
          "class": "fas fa-edit pull-right",
          "title": "Edit",
          "after": true,
          "selector": "a",
          "event": "click",
          "callback": function (node_id, node, action_id, action_el) {
            let jstree = $('#mapcontext_tree').jstree(true);
            jstree.edit(node.id);
          }
        });
      } else if (node.type === 'resource') {
        layerTree.add_action(node_id, {
          "id": "action_remove",
          "class": "fas fa-minus-circle pull-right",
          "title": "Remove",
          "after": true,
          "selector": "a",
          "event": "click",
          "callback": function (node_id, node, action_id, action_el) {
            let jstree = $('#mapcontext_tree').jstree(true);
            jstree.delete_node(node);
          }
        });
        layerTree.add_action(node_id, {
          "id": "action_edit",
          "class": "fas fa-edit pull-right",
          "title": "Edit",
          "after": true,
          "selector": "a",
          "event": "click",
          "callback": function (node_id, node, action_id, action_el) {
            $('#id_modal_owsresource').modal('show');
            $('#id_modal_owsresource').find('input[name="name"]').val(node.text);
            //$('#id_modal_owsresource').find('select[name="layer"]').val(node.data.wms_layer);
            let option = new Option(node.data.wms_layer.text, node.data.wms_layer.id, true, true);
            $('#id_modal_owsresource').find('select[name="layer"]').append(option).trigger('change');
            $('#id_modal_owsresource').find('select[name="layer"]').trigger({
              type: 'select2:select',
              params: {
                data: node.data.wms_layer
              }
            });
            $('#id_modal_owsresource').find('select[name="layer"]').trigger('change');
            $('#id_modal_owsresource form').off('submit');
            $('#id_modal_owsresource form').on('submit', function (event) {
              $('#mapcontext_tree').jstree('rename_node', node, $('#id_modal_owsresource').find('input[name="name"]').val());
              let data = $('#id_modal_owsresource').find('select[name="layer"]').select2('data')[0];
              debugger;
              node.data.wms_layer.id = data.id;
              node.data.wms_layer.text = data.text;
              update_layer_tree_input();
              $('#id_modal_owsresource').modal('hide');
              event.preventDefault();
            });
          }
        });
      }
    });
  });
});
