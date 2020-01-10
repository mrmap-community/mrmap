

/*
 * Function needs to stay outside of document.ready since there can be elements which have been added by js
 */
$(document).on("click", ".selected-value", function(){
    $(this).remove();
});

$(document).on("input.metadata-url", "input", function(){
    var elem = $(this);
    var inputs = $("input.metadata-url");
    var lastInput = inputs.last();
    var allFull = true;
    inputs.each(function(i, input){
        input = $(input);
        if(input.val().trim().length == 0){
            allFull = false;
            return;
        }
    });
    if(allFull){
        var newInput = $("<input/>")
            .attr("class", "metadata-url")
            .attr("type", "text");
        lastInput.after(newInput);
    }
});

/**
 * Sets the initial visibility of the secured selector elements
 */
function initializeSecuredFormStatus(){
    var isSecured = $("#id_is_secured").is(":checked");
    var securedSelectors = $(".secured-selector");
    var selectorParentRows = securedSelectors.closest("tr");
    var addGeometryButtons = selectorParentRows.find(".add-geometry");

    if(isSecured){
        securedSelectors.removeAttr("disabled")
        addGeometryButtons.removeAttr("disabled")
        selectorParentRows.removeClass("disabled");
    }else{
        securedSelectors.attr("disabled", "disabled")
        addGeometryButtons.attr("disabled", "disabled")
        selectorParentRows.addClass("disabled");
    }
}

function toggleSecuredCheckbox(){
    var elem = $("#checkbox-restrict-access");
    var checked = elem.is(":checked");
    var rows = $(".operation-row");
    var inputs = rows.find("input")
    var addGeometryButtons = rows.find(".add-geometry")
    if(checked){
        rows.removeClass("disabled");
        inputs.removeAttr("disabled");
        addGeometryButtons.removeAttr("disabled");
    }else{
        rows.addClass("disabled");
        inputs.attr("disabled", true);
        addGeometryButtons.attr("disabled", true);
    }
}

$(document).ready(function(){

    // set initial status for secured selectors
    initializeSecuredFormStatus();
    toggleSecuredCheckbox();

    $("#id_is_secured").on("change", function(){
        initializeSecuredFormStatus();
    });

    /**
    * If a group permission is changed, the GetFeatureInfo permission can not be set without the GetMap permission.
    * Make sure that GetFeatureInfo is linked to GetMap!
    */
    $(".group-permission").change(function(){
        var elem = $(this);
        var operation = elem.attr("data-operation");
        var group = elem.attr("data-group");
        var isElementChecked = elem.is(":checked");

        if(operation == "GetFeatureInfo"){
            // make sure that 'GetMap' is selected as well -> useless without!
            var getMapCheckbox = $(".group-permission[data-operation='GetMap'][data-group=" + group + "]")
            if(!getMapCheckbox.is(":checked") && isElementChecked){
                getMapCheckbox.click();
            }
        }
        if(operation == "GetMap"){
            // make sure that 'GetMap' is selected as well -> useless without!
            var getMapCheckbox = $(".group-permission[data-operation='GetFeatureInfo'][data-group=" + group + "]")
            if(getMapCheckbox.is(":checked") && !isElementChecked){
                getMapCheckbox.click();
            }
        }

        var securedId = parseInt(elem.attr("data-sec-id"));
        if(securedId != -1 && !isElementChecked){
            // this means the user wants to remove this secured operation setting!
            elem.attr("data-remove", true);
            console.log(securedId);

        }else if(securedId != -1 && isElementChecked){
            // this means the user has previously deselected this checkbox but changed it back to keep the secured operation setting!
            elem.attr("data-remove", false);
        }
    });


    $("#checkbox-restrict-access").change(function(){
        toggleSecuredCheckbox();
    });

    $("#checkbox-use-proxy").change(function(){
        var elem = $(this);
        // deactivate log proxy if use proxy is deactivated
        var logProxyElem = $("#checkbox-log-proxy")
        if(!elem.is(":checked") && logProxyElem.is(":checked")){
            logProxyElem.click();
        }
    });

    $("#checkbox-log-proxy").change(function(){
        var elem = $(this);
        // activate use proxy if log proxy is activated
        var useProxyElem = $("#checkbox-use-proxy")
        if(elem.is(":checked") && !useProxyElem.is(":checked")){
            useProxyElem.click();
        }
    });


    $(".submit-button.secured-operations").click(function(event){
        // store information as json into hidden input field
        var operations = $("ul")
        var hiddenInput = $("input.hidden");
        var txtArr = []
        operations.each(function(i, elem){
            elem = $(elem);
            var checkedElements = elem.find("input[id*='checkbox-sec-']:checked,input[id*='checkbox-sec-'][data-remove='true']");
            tmp = {
                "operation": elem.attr("data-operation"),
                "groups": [],
            }
            checkedElements.each(function(j, checkedElement){
                checkedElement = $(checkedElement);
                var dataSecId = checkedElement.attr("data-sec-id");
                var remove = checkedElement.attr("data-remove");
                if(dataSecId == ""){
                    dataSecId = -1;
                }

                // add groups and polygons
                tmpItem = {
                    "groupId": checkedElement.attr("data-group"),
                    "polygons": checkedElement.attr("data-polygons"),
                    "securedOperation": dataSecId,
                    "remove": checkedElement.attr("data-remove"),
                }
                tmp["groups"].push(tmpItem)

            });
            txtArr.push(tmp);
        });
        hiddenInput.val(JSON.stringify(txtArr));
    });

    $(".search-field").on("input", function(){
        var elem = $(this);
        var operation = elem.attr("data-type")
        var txt = elem.val();
        var elems = $("." + operation);
        elems.each(function(i, elem){
            elem = $(elem);
            txt = txt.toUpperCase();
            var label = elem.find("label").text().toUpperCase();
            if(label.includes(txt)){
                elem.show();
            }else{
                elem.hide();
            }
        });
    });


    $(".value-input").on("input", function(){
        var elem = $(this);
        var input = elem.val();
        var datalistOptions = elem.siblings("datalist").find("option");
        if(input.includes(",")){
            input = input.replace(",", "");
            var type = elem.parents("tr").attr("id");
            // if type != 'keywords' -> user is not allowed to add custom values
            if(type != 'keywords'){
                // check if the input is a word from the datalist
                var optionsArr = []
                datalistOptions.each(function(i, option){
                    optionsArr.push($(option).text())
                });
                if(!optionsArr.includes(input)){
                    alert("Please use only predefined values!");
                    return;
                }
            }
            elem.val("");
            var dataId = "-1"
            // find correct dataId of element, if it is a value from the datalist
            datalistOptions.each(function(i, option){
                if(input == option.text){
                    dataId = $(option).attr("data-id");
                    return;
                }
            });
            var wrapper = elem.siblings(".selected-values-wrapper");
            var wrapperElements = wrapper.find("span");
            var elementsArr = [];
            wrapperElements.each(function(i, elem){
                elementsArr.push($(elem).find(".value").text());
            });
            if(!elementsArr.includes(input)){
                wrapper.append('<span class="selected-value" data-id="' + dataId +'"><span class="value">' + input + '</span> &#x2716;</span>');
            }
        }
    });

    $("#metadata-form").submit(function(event){
        //event.preventDefault();
        // put iso metadata uris in correct input field
        var isoLinks = $("input.metadata-url");
        var isoLinkField = $("#iso-metadata-url");
        var linksArray = [];
        isoLinks.each(function(i, isoLink){
            isoLink = $(isoLink);
            if(isoLink.val().trim().length > 0){
                linksArray.push(isoLink.val());
            }
        });

        isoLinkField.append($('<input>', {
                    type: 'hidden',
                    name: "iso_metadata_url",
                    value: linksArray.join(",")
                })
                );

        // put keywords, categories and reference system in the correct input fields
        var names = $(["keywords", "categories"]);
        names.each(function(i, name){
            var itemRow = $("#" + name);
            var items = itemRow.find(".selected-value");
            var itemsArray = [];
            items.each(function(i, item){
                var tmp = "";
                if(name == "keywords"){
                    tmp = $(item).find(".value").text().trim();
                }else{
                    tmp = $(item).attr("data-id");
                }
                itemsArray.push(tmp);
            });
            itemRow.append($('<input>', {
                    type: 'hidden',
                    name: name,
                    value: itemsArray.join(",")
                })
            )
        });
        return true;
    });

    $(".add-geometry").click(function(){
        var elem = $(this);
        var serviceMetadataId = elem.attr("data-id")
        var operation = elem.siblings("input").attr("data-operation");
        var groupId = elem.siblings("input").attr("data-group");

        var existingPolygons = elem.siblings("input").attr("data-polygons");


        if(elem.attr("disabled") == "disabled"){
            return;
        }

        $.ajax({
            url: rootUrl + "/editor/edit/access/" + serviceMetadataId + "/geometry-form/",
            headers: {
                "X-CSRFToken": getCookie("csrftoken")
            },
            data: {
                "operation": operation,
                "groupId": groupId,
                "polygons": existingPolygons,
            },
            type: 'get',
            dataType: 'json'
        }).done(function(data){
            var html = data["html"];
            toggleOverlay(html);

        }).always(function(data){
            checkRedirect(data);
        });

    });
});