function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrftoken = getCookie('csrftoken');

function toggleOverlay(html){
    var overlay = $("#overlay");
    if(overlay.is(":visible")){
        overlay.html(html);
    }
    overlay.toggleClass("show");
}

$(document).on("click", "#eeImg", function(){
    toggleOverlay("");
    // restore rotation
    var elem = $("#ee-trggr");
    elem.css({"transform": "rotate(0deg)"});
});

function toggleBusyState( form ) {
  // get status message references
  const busyStateItems = form.querySelectorAll('.submit_btn_txt, .submit_btn_spinner');

  // Show busy state
  busyStateItems.forEach(function(item) {
    if ( item.classList.contains('d-none') ){
        item.classList.remove("d-none");
    } else {
        item.classList.add("d-none");
    }
  });

  // toggle disable state of all form elements to prevent further input
  Array.from(form.elements).forEach(function(field) {
    if ( field.disabled ) {
        field.disabled = false
    } else {
        field.disabled = true
    }
  });
}


function submitAsync( event, is_modal = false ) {
  const submitter = event.submitter;

  // Store reference to form and modal to make later code easier to read
  const form = event.target;
  const exchangeContainer = form.querySelector("div").closest(".modal-fetched-content")

  var formData = new FormData(form);
  if (submitter.name != ""){
    formData.append(submitter.name, "");
  }
  // Post data using the Fetch API
  fetch(form.action, {
      method: form.method,
      body: formData,
      redirect: 'manual'
    }).then(response => {
        if(response.ok) {
            return response;
        } else {
            throw Error(`Request rejected with status ${response.status}`);
        }
    }).then(response => {
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            return response.json().then(data => {
              // process your JSON data further
              if ( data.hasOwnProperty('data') ){
                if ( is_modal ) {
                    const modal = form.querySelector("div").closest(".modal")
                    $('#' + modal.id).modal('hide');
                }
                // todo: this should be fetched by a websocket
                document.querySelector("#body-content").insertAdjacentHTML('beforebegin', data.alert);
              } else {
                throw Error(`Response has no data attribute`);
              }
            });
        } else {
            return response.text().then(text => {
                // There is still a html content to render
                exchangeContainer.innerHTML = text;
                $('[data-toggle="tooltip"]').tooltip();
            });
        }
    }).catch(err => {
        if ( is_modal ) {
            const modal = form.querySelector("div").closest(".modal")
            $('#' + modal.id).modal('hide');
            exchangeContainer.innerHTML = "";
        }
        toggleBusyState( form );
        console.log(err);
    });

  toggleBusyState( form );

  // Prevent the default form submit
  event.preventDefault();
}

// adds auto submitting functionality to submit if a auto submit tagged item becomes changes
function isFormUpdateEventHandler( event ){
    const form = event.target.closest("form");
    const isFormUpdate = document.createElement("input");
    isFormUpdate.type = "hidden";
    isFormUpdate.name = "is_form_update";
    isFormUpdate.value = 'True'
    form.appendChild(isFormUpdate);
    form.querySelectorAll('[type=submit]')[0].click();
}

// adds formset delete form functionality to the frontend

function markFormAsDelete( submitter ){

    const formDeleteCheckbox = document.querySelector(submitter.dataset.target);
    const parentContainer = document.querySelector(submitter.dataset.parent);
    formDeleteCheckbox.value = "on";
    parentContainer.classList.add("d-none");

}

function ws_connect(path, search) {
    const ws_scheme = window.location.protocol == "https:" ? "wss" : "ws";
    const hostname = window.location.hostname;
    const port = window.location.port;
    var ws_socket = new WebSocket(ws_scheme + '://' + hostname + ':' + port + path + search);

    ws_socket.onopen = function open() {
        // do nothing if the websocket is correctly opened
    };

    ws_socket.onclose = function(e) {
        if (e.code > 1000){
            console.error('pending tasks socket closed unexpectedly');
            console.error(e);
        }
        // start reconnecting every 5 secs
        setTimeout(function() {
          connect();
        }, 5000);
    };

    return ws_socket
}

function update_pending_task_count(){
    var ws_socket = ws_connect('/ws/pending-tasks-count/', '')

    ws_socket.onmessage = function message(event) {
        var json_data = JSON.parse(JSON.parse(event.data));
        var span = document.getElementById("id_pending_tasks_count_nav_badge");
        span.textContent = json_data.running_tasks_count;

        if (json_data.running_tasks_count > 0){
            span.classList.remove("d-none");
        } else {
            span.classList.add("d-none");
        }
    };
}

$(document).ready(function(){
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

    $(function () {
      $('[data-toggle="tooltip"]').tooltip();
    })

    update_pending_task_count();
});