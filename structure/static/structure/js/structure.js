
$(document).ready(function(){
    $("#show-all").click(function(){
        var elem = $(this);
        var orgs = $(".subelements");
        orgs.toggle("slow");
        var img = elem.find("img");
        toggleCollapsibleSymbol(img);
    });
});