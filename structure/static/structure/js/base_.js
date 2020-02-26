function toggleOverlay(html){
    var overlay = $("#overlay");
    if(overlay.is(":visible")){
        overlay.html(html);
    }
    overlay.toggleClass("show");
}

function replaceButtonWithSpinner(button){
}

function changeOverlayContent(html){
    var overlay = $("#overlay");
    overlay.html(html);
}

$(document).on("click", "#eeImg", function(){
    toggleOverlay("");
    // restore rotation
    var elem = $("#ee-trggr");
    elem.css({"transform": "rotate(0deg)"});

});

$(document).ready(function(){

    var eeRotation = 0;

    $("#ee-trggr").mousemove(function(event){
        var element = $(this);
        // check if ctrl key is pressed
        eeRotation += 2;
        element.css({"transform": "rotate(" + eeRotation +"deg)"});
        if(eeRotation == 360){
            var eeSound = $("#ee-audio")[0];
            var img = $("<img/>").attr("src", "/static/structure/images/mr_map.png")
            .attr("class", "rotating-image")
            .attr("style", "object-fit: contain;")
            .attr("id", "eeImg");
            toggleOverlay(img);
            eeSound.addEventListener("ended", function(){
                // remove overlay
                if($("#overlay").hasClass("show")){
                    toggleOverlay("");
                }
            });
            eeSound.play();
            eeRotation = 0;
        }
    });

    $("#navbar-logo").mouseleave(function(){
        var elem = $(this);
        eeRotation = 0;
        elem.css({"transform": "rotate(" + eeRotation +"deg)"});
    });

});