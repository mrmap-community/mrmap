function sendPublishRequest(organizationId, entity){
    $.ajax({
        url: rootUrl + "/" + entity + "/organizations/publish-request/" + organizationId,
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {},
        type: 'get',
        dataType: 'json'
    }).done(function(data){
        var html = data["html"];
        toggleOverlay(html);
    }).always(function(data){
        checkRedirect(data);
    });
}



/**
*  JQuery content goes here!
*/
$(document).ready(function(){

    $("#show-all").click(function(){
        var elem = $(this);
        var orgs = $(".subelements");
        orgs.toggle("slow");
        var img = elem.find("img");
        toggleCollapsibleSymbol(img);
    });

    /**
    * Get request form for becoming a publisher to this organization
    */
    $("#request-publish-button").click(function(){
        var elem = $(this);
        var organizationId = elem.attr("datasrc");
        var entity = elem.attr("typeof")
        sendPublishRequest(organizationId, entity);
    });

});
