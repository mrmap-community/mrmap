function openNavigationMenu(elem){
    elem.slideToggle("fast");
}


$(document).ready(function(){
    $(".navigation-title").on("mouseover",function(){
        var list = $(this).siblings(".navigation-element-list");
        openNavigationMenu(list);
    });

    $(".navigation-menu").on("mouseleave",function(){
        var elem = $(this).find(".navigation-element-list");
        openNavigationMenu(elem);
    });

});