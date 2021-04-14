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
            console.error('socket closed unexpectedly');
            console.error(e);
        }
        // start reconnecting every 5 secs
        setTimeout(function() {
          connect();
        }, 5000);
    };

    return ws_socket
}

function handle_toast(){
    var ws_socket = ws_connect('/ws/toasts/', '')

    ws_socket.onmessage = function message(event) {
        var json_data = JSON.parse(event.data);
        var toast_container = document.getElementById("id_toast_container");
        toast_container.insertAdjacentHTML('beforeend', json_data.toast);
        console.log('something');
        $('.toast').toast('show')
        // add eventlistener to remove the toast from the dom after hiding
        $('.toast').on('hidden.bs.toast', function ( event ) {
          event.currentTarget.remove();
        })
    };
}


function AppViewModel() {
    var appViewModel = this;
    this.pendingTaskCount = ko.observable();

    var ws_socket = ws_connect('/ws/app-view-model/', '')
    ws_socket.onmessage = function message(event) {
        var json_data = JSON.parse(event.data);
        for (const observable of Object.getOwnPropertyNames(appViewModel)) {
            appViewModel[observable](json_data[observable]);
        }
    };
}

window.addEventListener('load', function () {
  // Activates knockout.js
  var appViewModel = new AppViewModel();
  ko.applyBindings(appViewModel);

  handle_toast();
})


