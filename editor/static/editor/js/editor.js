

/*
 * Function needs to stay outside of document.ready since there can be elements which have been added by js
 */
$(document).on("click", ".selected-value", function(){
    $(this).remove();
});

$(document).ready(function(){

    $(".value-input").on("input", function(){
        var elem = $(this);
        var input = elem.val();
        if(input.includes(",")){
            input = input.replace(",", "");
            var type = elem.parents("tr").attr("id");
            // if type != 'keywords' -> user is not allowed to add custom values
            if(type != 'keywords'){
                // check if the input is a word from the datalist
                var options = elem.siblings("datalist").find("option");
                var optionsArr = []
                options.each(function(i, option){
                    optionsArr.push($(option).text())
                });
                if(!optionsArr.includes(input)){
                    alert("Please use only predefined values!");
                    return;
                }
            }
            elem.val("");
            var wrapper = elem.siblings(".selected-values-wrapper");
            var wrapperElements = wrapper.find("span").text().replace(" ", "").replace("✖", "");
            if(!wrapperElements.includes(input)){
                wrapper.append('<span class="selected-value" data-id="' + '-1' +'">' + input + ' &#x2716;</span>');
            }
        }
    });

    $("#metadata-form").submit(function(event){
        //event.preventDefault();
        // put keywords, categories and reference system in the correct input labels
        var names = $(["keywords", "categories", "reference_system"]);
        names.each(function(i, name){
            var itemRow = $("#" + name);
            var items = itemRow.find(".selected-value");
            var itemsArray = [];
            items.each(function(i, item){
                var id = $(item).attr("data-id");
                itemsArray.push(id);
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