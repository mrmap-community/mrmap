
$(document).ready(function(){
    $("#show-all-organizations").click(function(){
        var elem = $(this);
        var orgs = $("#all-organizations");
        orgs.toggle("slow");
        var img = elem.find("img");
        toggleCollapsibleSymbol(img);
    });
});