
function getCookie(cname) {
    var name = cname + "=";
    var decodedCookie = decodeURIComponent(document.cookie);
    var ca = decodedCookie.split(';');
    for(var i = 0; i <ca.length; i++) {
        var c = ca[i];
        while (c.charAt(0) == ' ') {
            c = c.substring(1);
        }
        if (c.indexOf(name) == 0) {
            return c.substring(name.length, c.length);
        }
    }
    return "";
}

function toggleNavigationMenu(elem){
    elem.slideToggle("fast");
}

$(document).ready(function(){
    $(".navigation-menu").on("mouseover",function(){
        var list = $(this).find(".navigation-element-list");
        if(list.is(":hidden")){
            toggleNavigationMenu(list);
        }
    });

    $(".navigation-menu").on("mouseleave",function(){
        var elem = $(this).find(".navigation-element-list");
        if(!elem.is(":hidden")){
            toggleNavigationMenu(elem);
        }
    });

    $(".messages").on("click", function(){
        var elem = $(this);
        elem.slideToggle();
    });

});