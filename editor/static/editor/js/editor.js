

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

    if(isSecured){
        securedSelectors.removeAttr("disabled")
        selectorParentRows.removeClass("disabled");
    }else{
        securedSelectors.attr("disabled", "disabled")
        selectorParentRows.addClass("disabled");
    }
}

function toggleSecuredCheckbox(){
    var elem = $("#checkbox-restrict-access");
    var checked = elem.is(":checked");
    var rows = $(".operation-row");
    var inputs = rows.find("input")
    if(checked){
        rows.removeClass("disabled");
        inputs.removeAttr("disabled");
    }else{
        rows.addClass("disabled");
        inputs.attr("disabled", true);
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

        if(operation == "GetFeatureInfo"){
            // make sure that 'GetMap' is selected as well -> useless without!
            var getMapCheckbox = $(".group-permission[data-operation='GetMap'][data-group=" + group + "]")
            if(!getMapCheckbox.is(":checked") && elem.is(":checked")){
                getMapCheckbox.click();
            }
        }
        if(operation == "GetMap"){
            // make sure that 'GetMap' is selected as well -> useless without!
            var getMapCheckbox = $(".group-permission[data-operation='GetFeatureInfo'][data-group=" + group + "]")
            if(getMapCheckbox.is(":checked") && !elem.is(":checked")){
                getMapCheckbox.click();
            }
        }
    });


    $("#checkbox-restrict-access").change(function(){
        toggleSecuredCheckbox();
    });

    $(".submit-button.secured-operations").click(function(event){
        // store information into hidden input field as json
        var checkedElements = $("input[id*='checkbox-sec-']:checked");
        var hiddenInput = $("input.hidden");
        var txt = '[';
        var txtArr = []
        checkedElements.each(function(i, elem){
            elem = $(elem);
            var elemTxt = '{"operation": "' + elem.attr("data-operation") + '", "group": ' + elem.attr("data-group") + '}';
            txtArr.push(elemTxt);
        });
        txt += txtArr.join(",");
        txt += "]"
        console.log(txt);
        hiddenInput.val(txt);
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
});