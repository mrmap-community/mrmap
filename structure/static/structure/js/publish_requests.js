function toggleRequest(accept, requestId, organizationId){
    $.ajax({
        url: rootUrl + "/structure/organizations/toggle-publish-request/" + organizationId,
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {
            "accept": accept,
            "requestId": requestId
        },
        type: 'post',
        dataType: 'json'
    }).done(function(data){

    }).always(function(data){
        checkRedirect(data);
    });
}

function removePublisher(orgId, groupId){
    $.ajax({
        url: rootUrl + "/structure/organizations/remove-publisher/" + orgId,
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {
            "publishingGroupId": groupId
        },
        type: 'post',
        dataType: 'json'
    }).done(function(data){

    }).always(function(data){
        checkRedirect(data);
    });
}



$(document).ready(function(){

    $("#accept-request").click(function(){
        var elem = $(this);
        var requestId = elem.parents("tr").attr("data-id");
        var organizationId = elem.parents("tr").attr("data-parent");
        toggleRequest(true, requestId, organizationId);
    });

    $("#decline-request").click(function(){
        var elem = $(this);
        var requestId = elem.parents("tr").attr("data-id");
        var organizationId = elem.parents("tr").attr("data-parent");
        toggleRequest(false, requestId, organizationId);
    });

    $(".delete-container").click(function(){
        var elem = $(this);
        var publisherGroupId = elem.attr("data-id");
        var publishesForOrganizationId = elem.attr("data-parent");
        removePublisher(publisherGroupId, publishesForOrganizationId);
    });
});