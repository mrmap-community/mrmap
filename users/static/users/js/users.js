function decreaseSecond(){
    var secCounter = $("#seconds-counter");
    var val = parseInt(secCounter.text());
    if(val == 0){
        window.location.pathname = "/";
    }else{
        secCounter.text(val-1);
    }
}

/*
* Count down the seconds until the user will be forwarded
*/
function redirectToLoginAfterTime(){
    var secCounter = $("#seconds-counter");
    // set seconds to wait
    secCounter.text(10);
    setInterval(decreaseSecond, 1000)

}


$(document).ready(function(){
    redirectToLoginAfterTime();

});