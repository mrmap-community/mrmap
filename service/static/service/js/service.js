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

function removeService(id, confirmed){
    $.ajax({
        url: "/service/remove",
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
            console.log(data);
            if(data["redirect"] !== null){
                window.open(data["redirect"], "_self");
            }

        }
    })

}

function startServiceRegistration(uri){
    $.ajax({
        url: "/service/new/",
        headers:{
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {
            "uri": uri
        },
        type: 'post',
        dataType: 'json',
        success: function(data){
            changeOverlayContent(data["html"]);
        }
    });

}

function checkServiceRequestURI(){
    var uri = $("#request-uri input").val().trim();
    if (uri.length == 0){
        return
    }
    if (!uri.startsWith("http://")){
        uri = "http://" + uri;
    }
    $.ajax({
        url: "/service/new/register-form",
        headers:{
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {
            "uri": uri
        },
        type: 'post',
        dataType: 'json',
        success: function(data){
            changeOverlayContent(data["html"]);
        }
    });
}

function toggleCollapsibleSymbol(elem){
    var src = elem.attr("src");
    var toggle = elem.attr("data-toggle");
    elem.attr("src", toggle);
    elem.attr("data-toggle", src);
}

$(document).ready(function(){
    $(".remove-service-container").click(function(){
        var id = $(this).attr("data-parent");
        // call remove form, but indicate that the remove process was not confirmed yet by the user
        removeService(id, false);
    });


    $("#service-display-selector").change(function(){
        var val = $(this).val();
        $.ajax({
            url: "/service/session",
            headers: {
                "X-CSRFToken": getCookie("csrftoken")
            },
            data:{
                "session": JSON.stringify({
                    "displayServices": val
                })
            },
            type: 'get',
            dataType: 'json',
            success: function(data){
                location.reload();
            }

        });


    });

    $(".action-button").click(function(){
        $.ajax({
            url: "/service/new/register-form",
            headers: {
                "X-CSRFToken": getCookie("csrftoken")
            },
            data: {},
            type: 'get',
            dataType: 'json',
            success: function(data) {
                var html = data["html"];
                toggleOverlay(html);
            }
        });
    });

    $(".layer-title").click(function(){
        var elem = $(this);
        var table = elem.siblings(".layer-content");
        table.toggle("fast");
        var img = elem.find("img");
        toggleCollapsibleSymbol(img);
    });

});