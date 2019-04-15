function toggleNavigationMenu(elem){
    elem.slideToggle("fast");
}


$(document).ready(function(){
    $(".navigation-title").on("mouseover",function(){
        var list = $(this).siblings(".navigation-element-list");
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

});