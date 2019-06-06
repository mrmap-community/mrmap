/**
*  Load draggable element identifier into event arguments
*/
function drag(ev){
    ev.dataTransfer.setData("id", ev.target.id);
}

/**
*  Allow the drop on target element
*/
function allowDrop(ev){
    ev.preventDefault();
}

/**
*  Let the element be dropped back into it's original parent
*/
function dropBack(ev){
    ev.preventDefault();
    var id = ev.dataTransfer.getData("id")
    var target = $(ev.target);
    var targetId = target.attr("id");
    // check if this item is allowed in here
    var allowedId = target.attr("itemid");
    if(allowedId != id){
        // stop!
        return;
    }
    var draggedElement = $(document.getElementById(id));
    var removedSiblingId = draggedElement.siblings(".update.removed").attr("id");
    // delete arrow
    draggedElement.prev().remove();
    window.sessionStorage.removeItem(id);

    target.html(draggedElement);
}

/**
*  Same as dropBack() but is fired on doubleclicking the element
*/
function autoDropBack(target, element){
    var id = element.attr("id")
    // check if this item is allowed in here
    var allowedId = target.attr("itemid");
    var draggedElement = $(document.getElementById(id));
    var removedSiblingId = draggedElement.siblings(".update.removed").attr("id");
    // delete arrow
    draggedElement.prev().remove();
    target.html(draggedElement);
    window.sessionStorage.removeItem(id);
}

/**
*  Position the dragged element next to the current one
*/
function dropNewLayer(ev){
    ev.preventDefault();
    var id = ev.dataTransfer.getData("id")
    var target = $(ev.target);
    var targetId = target.attr("id");
    var parent = target.parent();
    if(parent.find(".update.new").length > 0){
        // there is only at least one element in here. Do not continue!
        return;
    }
    window.sessionStorage.setItem(id, targetId);
    var draggedElement = $(document.getElementById(id));
    draggedElement.insertAfter(target);
    draggedElement.before("<span> &rarr; </span>");
}



$(document).ready(function(){
    // clear sessionStorage on every page reload
    window.sessionStorage.clear();

    /**
    *  Listener for doubleclicks
    */
    $(".update.new").dblclick(function(){
        // reset new layer to original place if it is currently linked to an old layer
        var element = $(this);
        var id = element.attr("id");
        var parent = element.parent().parent();
        if(parent.hasClass("old-service")){
            // yes, put it back to where it belongs!
            var origins = $(".new-service td");
            // find matching itemid element without using jquery.
            // Why without jquery? Because the ids might contain ':' which is prohibited in jquery selectors -> we can not use it
            var origin = null;
            origins.each(function(i){
                var item = origins[i];
                if(item.getAttribute("itemid") == id){
                    // the element we want
                    origin = item;
                }
            });
            // transform found origin back to jquery object
            origin = $(origin);
            autoDropBack(origin, element);
        }
    });

});