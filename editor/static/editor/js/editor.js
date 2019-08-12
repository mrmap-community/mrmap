

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

$(document).ready(function(){


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