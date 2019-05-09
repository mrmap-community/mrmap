


function toggleServiceActiveStatus(id, active){
    $.ajax({
        url: "/service/activate/",
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data:{
            "id": id,
            "active": active
        },
        type: 'post',
        dataType: 'json',
        success: function(data){
            location.reload();
        }
    })
}

function startServiceRegistration(uri, button){
    var oldHtml = button.html();
    button.html("Please wait...");
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
            button.html(oldHtml);
        },
        always: function(data){
            $(".loading-spinner").toggleClass("hide");
        }
    });

}

function checkServiceRequestURI(){
    var uri = $("#request-uri input").val().trim();
    if (uri.length == 0){
        return
    }
    if (!uri.startsWith("http")){
        uri = "http://" + uri; // use http by default
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

    $(".deactivate-container, .activate-container").click(function(){
        var id = $(this).attr("data-parent");
        var elem = $(this);
        var active = false;
        if(elem.hasClass("activate-container")){
            var active = true;
        }
        toggleServiceActiveStatus(id, active)
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
            contentType: 'application/json',
            type: 'get',
            dataType: 'json',
        }).done(function(){
            location.reload();

        }).fail(function(jqXHR, textStatus){
            console.log(textStatus);
            console.log(jqXHR);
        });
    });

    $(".add-button").click(function(){
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

    $(".sublayer-headline").click(function(){
        var elem = $(this);
        var table = elem.siblings(".sublayer");
        table.toggle("fast");
        var img = elem.find("img");
        toggleCollapsibleSymbol(img);
    });

});