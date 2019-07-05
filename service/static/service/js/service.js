


function toggleServiceActiveStatus(id, active){
    $.ajax({
        url: rootUrl + "/service/activate/",
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data:{
            "id": id,
            "active": active
        },
        type: 'post',
        dataType: 'json',
    })
    .done(function(data){
        //location.reload();
    })
    .always(function(data){
        checkRedirect(data);
    });
}

function startServiceRegistration(uri, registerGroup, registerForOrg, button){
    var oldHtml = button.html();
    button.html("Please wait...");
    $.ajax({
        url: rootUrl + "/service/new/",
        headers:{
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {
            "uri": uri,
            "registerGroup": registerGroup,
            "registerForOrg": registerForOrg
        },
        type: 'post',
        dataType: 'json'
    })
    .done(function(data){
        changeOverlayContent(data["html"]);
        button.html(oldHtml);
    })
    .always(function(data){
        checkRedirect(data);
    });
}

function startServiceUpdate(uri, button, id){
    var oldHtml = button.html();
    button.html("Please wait...");
    /*
    $.ajax({
        url: rootUrl + "/service/update/" + id,
        headers:{
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {
            "uri": uri
        },
        type: 'post',
        dataType: 'json'
    })
    .done(function(data){
        changeOverlayContent(data["html"]);
        button.html(oldHtml);
    })
    .always(function(data){
        checkRedirect(data);
    });
    */
}

function checkServiceRequestURI(isUpdate, id){
    var uri = $("#request-uri input").val().trim();
    if (uri.length == 0){
        return
    }
    var url = "";
    if(isUpdate){
        url = rootUrl + "/service/update/register-form/" + id;
    }else{
        url = rootUrl + "/service/new/register-form";
    }
    if (!uri.startsWith("http")){
        uri = "http://" + uri; // use http by default
    }
    $.ajax({
        url: url,
        headers:{
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {
            "uri": uri
        },
        type: 'post',
        dataType: 'json'
    })
    .done(function(data){
        changeOverlayContent(data["html"]);
    })
    .always(function(data){
        checkRedirect(data);
    });
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
            url: rootUrl + "/service/session",
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
        }).always(function(data){
            checkRedirect(data);
        });
    });

    $(".layer-title").click(function(){
        var elem = $(this);
        var table = elem.siblings(".subelements");
        var layerId = elem.attr("data-id");
        if(!elem.hasClass("loaded")){
            // do the ajax request
            $.ajax({
                url: rootUrl + "/service/detail-child/" + layerId,
                headers: {
                    "X-CSRFToken": getCookie("csrftoken")
                },
                data: {},
                type: 'get',
                dataType: 'json'
            }).done(function(data){
                var html = data["html"];
                console.log(html);
                table.html(html);
                elem.addClass("loaded");
            }).always(function(data){
            });
        }
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

    $("#service-update-button").click(function(){
        var entity = $(this).attr("typeof");
        var id = $(this).attr("datasrc");
        updateEntity(id, entity);
    });

});