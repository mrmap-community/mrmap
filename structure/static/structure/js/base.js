
function getCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function toggleNavigationMenu(elem){
    elem.slideToggle("fast");
}

function toggleOverlay(html){
    var overlay = $("#overlay");
    if(overlay.is(":visible")){
        overlay.html(html);
    }
    overlay.toggleClass("show");
}

function replaceButtonWithSpinner(button){
}

function changeOverlayContent(html){
    var overlay = $("#overlay");
    overlay.html(html);
}


function editEntity(id, entity){
    $.ajax({
        url: "/" + entity + "/edit/" + id,
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {},
        type: 'get',
        dataType: 'json',
        success: function(data){
            var html = data["html"];
            toggleOverlay(html);
        }
    })
}

function addEntity(entity){
    $.ajax({
        url: "/" + entity + "/new/",
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {},
        type: 'get',
        dataType: 'json',
        success: function(data){
            var html = data["html"];
            toggleOverlay(html);
        }
    })
}


function removeEntity(id, confirmed, entity){
    $.ajax({
        url: "/" + entity + "/remove",
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data:{
            "id": id,
            "confirmed": confirmed
        },
        type: 'get',
        dataType: 'json',
        success: function(data){
            var html = data["html"];
            toggleOverlay(html);
            if(data["redirect"] !== null){
                window.open(data["redirect"], "_self");
            }
        }
    })
}

$(document).ready(function(){
    $(".navigation-menu").on("mouseover",function(){
        var list = $(this).find(".navigation-element-list");
        if(list.is(":hidden")){
            toggleNavigationMenu(list);
        }
    });

    $(".navigation-menu").on("mouseleave",function(){
        var elem = $(this).find(".navigation-element-list");
        if(!elem.is(":hidden")){
            toggleNavigationMenu(elem);
        }
    });

    $(".messages").on("click", function(){
        var elem = $(this);
        elem.slideToggle();
    });

    $(".delete-container").click(function(){
        var id = $(this).attr("data-parent");
        // call remove form, but indicate that the remove process was not confirmed yet by the user
        var entity = $(this).attr("typeof");
        removeEntity(id, false, entity);
    });

    $(".edit-container").click(function(){
        var id = $(this).attr("data-parent");
        // call remove form, but indicate that the remove process was not confirmed yet by the user
        var entity = $(this).attr("typeof");
        editEntity(id, entity);
    });

    $(".add-button").click(function(){
        // call remove form, but indicate that the remove process was not confirmed yet by the user
        var entity = $(this).attr("typeof");
        addEntity(entity);
    });


});