
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

/**
 * Setter for the session storage
 */
function setSessionValue(key, value){
    window.sessionStorage.setItem(key, value);
}
/**
 * Getter for the session storage
 *      using the parameter 'remove', the key-value pair will be deleted afterwards
 */
function getSessionValue(key, remove){
    var item = window.sessionStorage.getItem(key);
    if(remove){
        window.sessionStorage.removeItem(key);
    }
    return item;
}

function findSessionValuesLike(substring){
    var items = window.sessionStorage;
    var retArr = [];
    for(i = 0; i < items.length; i++){
        if(items.key(i).includes(substring)){
            retArr.push(getSessionValue(items.key(i)));
        }
    }
    return retArr;
}

function findSessionKeysLike(substring){
    var items = window.sessionStorage;
    var retArr = [];
    for(i = 0; i < items.length; i++){
        if(items.key(i).includes(substring)){
            retArr.push(items.key(i));
        }
    }
    return retArr;
}

function removeSessionKeysLike(substring){
    var items = window.sessionStorage;
    for(i = 0; i < items.length; i++){
        if(items.key(i).includes(substring)){
            getSessionValue(items.key(i), true);
        }
    }
}


function toggleCollapsibleSymbol(elem){
    var src = elem.attr("src");
    var toggle = elem.attr("data-toggle");
    elem.attr("src", toggle);
    elem.attr("data-toggle", src);
}

function checkRedirect(data){
    if(data["redirect"] !== null){
        window.open(data["redirect"], "_self");
    }
}

function toggleNavigationMenu(elem){
    elem.toggleClass("open");
    elem.stop(true, true).slideToggle("medium");
}

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


function editEntity(id, entity){
    $.ajax({
        url: rootUrl + "/" + entity + "/edit/" + id,
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {},
        type: 'get',
        dataType: 'json'
    }).done(function(data){
        var html = data["html"];
        toggleOverlay(html);
    }).always(function(data){
        checkRedirect(data);
    });
}

function updateEntity(id, entity){
    $.ajax({
        url: rootUrl + "/" + entity + "/update/register-form/" + id,
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {},
        type: 'get',
        dataType: 'json'
    }).done(function(data){
        var html = data["html"];
        toggleOverlay(html);

    }).always(function(data){
        checkRedirect(data);
    });
}

function addEntity(entity){
    $.ajax({
        url: rootUrl + "/" + entity + "/new/register-form",
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        data: {},
        type: 'get',
        dataType: 'json',
    }).done(function(data){
        var html = data["html"];
        toggleOverlay(html);
    }).always(function(data){
        checkRedirect(data);
    });
}


function removeEntity(id, confirmed, entity){
    $.ajax({
        url: rootUrl + "/" + entity + "/remove?id=" + id + "&confirmed=" + confirmed,
        headers: {
            "X-CSRFToken": getCookie("csrftoken")
        },
        type: 'get',
        dataType: 'json'
    }).done(function(data){
        var html = data["html"];
        toggleOverlay(html);
    }).always(function(data){
        checkRedirect(data);
    });
}

$(document).on("click", "#eeImg", function(){
    toggleOverlay("");
    // restore rotation
    var elem = $("#ee-trggr");
    elem.css({"transform": "rotate(0deg)"});
});


$(document).ready(function(){
    // hide messages after 10 seconds automatically
    setTimeout(function(){
        var msg = $(".messages");
        if(msg.is(":visible")){
            $(".messages").click();
        }
    }, 5000);

    var eeRotation = 0;

    $("#ee-trggr").mousemove(function(event){
        var element = $(this);
        // check if ctrl key is pressed
        eeRotation += 2;
        element.css({"transform": "rotate(" + eeRotation +"deg)"});
        if(eeRotation == 360){
            var eeSound = $("#ee-audio")[0];
            var img = $("<img/>").attr("src", "/static/images/mr_map.png")
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


    $(".navigation-menu").on("mouseover",function(){
        var list = $(this).find(".navigation-element-list");
        if(!list.hasClass("open")){
            toggleNavigationMenu(list);
        }
    });

    $(".navigation-menu").on("mouseleave",function(){
        var elem = $(this).find(".navigation-element-list");
        if(elem.hasClass("open")){
            toggleNavigationMenu(elem);
        }
    });

    $(".messages").on("click", function(){
        var elem = $(this);
        elem.slideToggle();
    });

    $(".delete-container").click(function(){
        var id = $(this).attr("data-parent");
        // call remove form, but indicate that the remove process was not confirmed yet by the user
        var entity = $(this).attr("typeof");
        removeEntity(id, false, entity);
    });

    $("#edit-button, #change-pw-button").click(function(){
        var id = $(this).attr("data-parent");
        // call remove form, but indicate that the remove process was not confirmed yet by the user
        var entity = $(this).attr("typeof");
        if(entity.includes('user')){
            id = "";
        }
        editEntity(id, entity);
    });

    $(".add-button").click(function(){
        // call remove form, but indicate that the remove process was not confirmed yet by the user
        var entity = $(this).attr("typeof");
        addEntity(entity);
    });

    $("html").click(function(){
        var langMenu = $("#current-lang");
        if(langMenu.hasClass("open")){
            langMenu.click();
        }
    });

    $("#current-lang").click(function(event){
        event.stopPropagation();
        var elem = $(this);
        elem.toggleClass("open");
        $("#lang-selector").slideToggle();
    });


    $(".lang-item").click(function(){
        var elem = $(this);
        var val = elem.attr("data-value");
        // activate selected language via ajax call
        $.ajax({
            url: "/i18n/setlang/",
            headers: {
                "X-CSRFToken": getCookie("csrftoken")
            },
            data: {
                'language': val
            },
            type: 'post',
            dataType: 'json',
            success: function(data) {
                location.reload();
            },
            timeout: 10000,
            error: function(jqXHR, textStatus, errorThrown){
                if(textStatus === "timeout"){
                    console.log("A timeout occured.");
                }
            }
        })

    });

    $(function () {
      $('[data-toggle="tooltip"]').tooltip()
    })

});


function asyncForm( event ) {
  // Store reference to form and modal to make later code easier to read
  const form = event.target;
  const modal = form.querySelector("div").closest(".modal")
  const modalContent = form.querySelector("div").closest(".modal-content")


  // get status message references
  const submitBtnTxt = form.querySelector('#id_submit_btn_txt');
  const submitBtnSpinner = form.querySelector('#id_submit_btn_spinner');

  // Post data using the Fetch API
  fetch(form.action, {
      method: form.method,
      body: new FormData(form)
    }).then(res => {
        if(res.ok) {
            // all done. Close modal.
            $('#' + modal.id).modal('hide');
            return res.json();
        } else {
            if ( res.status >= 400 && res.status <= 500) {
                return res.json();
            } else {
                $('#' + modal.id).modal('hide');
                throw Error(`Request rejected with status ${res.status}`);
            }
        }
    }).then(json => {
        if (json.hasOwnProperty('data')){
            modalContent.innerHTML = json.data;
        } else if (json.hasOwnProperty('task')){
            document.querySelector("#body-content").insertAdjacentHTML('beforebegin', json.task.alert);
        }

    }).catch(err => {
        console.log(err);
    });

  // Show busy state
  submitBtnTxt.classList.add("d-none");
  submitBtnSpinner.classList.remove("d-none");

  // Disable all form elements to prevent further input
  Array.from(form.elements).forEach(field => field.disabled = true);

  // Prevent the default form submit
  event.preventDefault();
}