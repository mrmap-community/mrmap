
function checkTaskStatus(tasks){
    tasks.each(function(i, task){
        task = $(task);
        // run delayed requests for task progress
        var interval = setInterval(function(){
            var progressBar = task.find(".fg");
            var taskId = progressBar.attr("data-id");
            var phaseElem = task.find(".task-phase");
            var descriptionElem = task.find(".task-description");
            var loadingSpinner = task.find(".loading-spinner");
            var numberElement = task.find(".number");
            $.ajax({
                url: rootUrl + "/structure/task/",
                headers: {
                    "X-CSRFToken": getCookie("csrftoken")
                },
                data:{
                    "id": taskId,
                },
                type: 'get',
                dataType: 'json',
            })
            .done(function(data){
                var task = data["task"];
                var progress = task["info"];
                var description = JSON.parse(task["description"]);
                // set phase and service name
                if(description.service.length > 0){
                    descriptionElem.html(description.service);
                }
                if(description.phase.length > 0){
                    phaseElem.html(description.phase);
                }
                if(progress != null){
                    progress = progress["current"];
                    // write new progress to bar
                    var pgNum = progress + "%";
                    progressBar.css("width", pgNum);
                    numberElement.html(pgNum)
                    if(progress == 100){
                        // we are done!
                        clearInterval(interval);
                        loadingSpinner.hide();
                        location.reload();
                    }
                }
            })
            .always(function(data){
            });
        }, 1000);

    });

}


$(document).ready(function(){
    // check for pending task html elements
    var tasks = $("tr[data-type='pending-task']");
    if(tasks.length > 0){
        checkTaskStatus(tasks);
    }

});