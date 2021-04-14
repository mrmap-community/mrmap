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

function handle_toast(){
    var ws_socket = ws_connect('/ws/toasts/', '')

    ws_socket.onmessage = function message(event) {
        var json_data = JSON.parse(JSON.parse(event.data));
        var toast_container = document.getElementById("id_toast_container");
        toast_container.insertAdjacentHTML('beforeend', json_data.toast);
        console.log('something');
        $('.toast').toast('show')
    };
}

window.addEventListener('load', function () {
  update_pending_task_count();
  handle_toast();
})


