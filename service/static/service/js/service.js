


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

/**
 * Starts an ajax request to the server and loads the table content
 */
function getTableContent(elem, elemId, elemType, table){
    $.ajax({
        url: rootUrl + "/service/detail-child/" + elemId,
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {
            "serviceType": elemType
        },
        type: 'get',
        dataType: 'json'
    }).done(function(data){
        var html = data["html"];
        var contentDiv = table.find(".content");
        contentDiv.html(html);
        elem.addClass("loaded");
    }).always(function(data){
    });
}

/**
 * Starts an ajax request to the server and checks if the processed subelement has a dataset metadata related to.
 * If so, the dataset metadata button will be displayed
 */
function toggleDatasetMetadataButton(elemId, elemType, table){
    $.ajax({
        url: rootUrl + "/service/metadata/dataset/check/" + elemId,
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {
            "serviceType": elemType
        },
        type: 'get',
        dataType: 'json'
    }).done(function(data){
        var hasDatasetMetadata = data["has_dataset_doc"];
        if(hasDatasetMetadata){
            // show the dataset metadata button
            var selector = 'a[data-id="' + elemId + '"]';
            var button = table.find(selector);
            button.toggleClass("hide");
        }
    }).always(function(data){
    });
}


/*
 *  THESE FUNCTIONS HAVE TO STAY OUTSIDE THE DOCUMENT.READY BLOCK
 *  THIS IS DUE TO THE FACT THAT THESE HAVE TO BE FIRED FOR AJAX LOADED HTML CONTENT AS WELL, WHICH WILL NOT WORK IF
 *  THEY WOULD BE INSIDE THE DOCUMENT.READY BLOCK
 */
$(document).on("click", ".layer-title", function(){
    var elem = $(this);
    var table = elem.siblings(".subelements");
    var elemId = elem.attr("data-id");
    var elemType = elem.attr("data-type");
    if(!elem.hasClass("loaded") && elemType != "featureTypeElements"){
        // do the ajax request for loading the detail view table content
        getTableContent(elem, elemId, elemType, table);

        // do the ajax request for loading the dataset metadata button
        toggleDatasetMetadataButton(elemId, elemType, table);
    }
    table.toggle("fast");
    var img = elem.find(".collapse-img");
    toggleCollapsibleSymbol(img);
});

/*
 *  THESE FUNCTIONS HAVE TO STAY OUTSIDE THE DOCUMENT.READY BLOCK
 *  THIS IS DUE TO THE FACT THAT THESE HAVE TO BE FIRED FOR AJAX LOADED HTML CONTENT AS WELL, WHICH WILL NOT WORK IF
 *  THEY WOULD BE INSIDE THE DOCUMENT.READY BLOCK
 */
$(document).on("click", ".sublayer-headline", function(){
    var elem = $(this);
    var table = elem.siblings(".sublayer");
    table.toggle("fast");
    var img = elem.find("img");
    toggleCollapsibleSymbol(img);
});

function changeGetParam(param, newVal){
    var query = location.search;
    var params = new URLSearchParams(query);
    params.set(param, newVal);
    query = params.toString();
    location.search = query;
}

$(document).ready(function(){

    $(".rpp-select").change(function(){
        var val = $(this).val();
        changeGetParam("rpp", val);
    });

    $(".pagination-input").change(function(){
        var val = $(this).val();
        var type = $(this).attr("data-type");
        changeGetParam(type, val);
    });

    $("#service-display-selector").change(function(){
        var val = $(this).val();
        var currentUrl = new URL(location.href);
        var newUrlParams = new URLSearchParams(currentUrl.search);
        newUrlParams.set("q", val);
        location.search = newUrlParams.toString();
    });

    $("#service-update-button").click(function(){
        var entity = $(this).attr("typeof");
        var id = $(this).attr("datasrc");
        updateEntity(id, entity);
    });


    $(".search-field").on("input", function(){
        var elem = $(this);
        var input = elem.val().toUpperCase();
        var type = elem.attr("data-type");
        var services = $(".service[data-type='" + type + "']");
        services.each(function(i, service){
            service = $(service);
            var title = service.find("[data-type='title']").text().trim().toUpperCase();
            var parentService = service.find("[data-type='parent-service']").text().trim().toUpperCase();
            if(title.includes(input) || parentService.includes(input)){
                service.show();
            }else{
                service.hide();
            }
        });
    });

    $(document).on("click", ".collapsible-toggler", function(event){
        event.stopPropagation();
        var elem = $(this);
        var list = elem.siblings(".collapsible-list");
        elem.toggleClass("open");
        list.slideToggle();
    });

    $(document).on("click", "html", function(){
        var toggler = $(".collapsible-toggler");
        toggler.each(function(i, elem){
            elem = $(elem);
            if(elem.hasClass("open")){
                elem.toggleClass("open");
                elem.siblings(".collapsible-list").slideToggle();
            }
        });
    });



});