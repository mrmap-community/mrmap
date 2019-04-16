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
            console.log(data["html"]);
        }
    });

}

function checkServiceRequestURI(){
    var uri = $("#request-uri input").val();
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

$(document).ready(function(){
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

});