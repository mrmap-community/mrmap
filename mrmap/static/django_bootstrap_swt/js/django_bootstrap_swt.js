function bootstrapComponentAjaxCall( target, target_body , modal) {
    var fetch_url = target.attributes.getNamedItem('data-url').value;
    var tooltips = $('[data-toggle="tooltip"]', target);
    const spinner = target_body.children(".django-bootstrap-swt-spinner");
    const error = target_body.closest(".django-bootstrap-swt-error");

    if ( modal ){
        target_body = $(".modal-fetched-content", target_body);
    }

    tooltips.tooltip("hide");
    $.ajax({
      url: fetch_url,
      beforeSend: function() {
        spinner.removeClass("d-none");
      },
      success: function( data ) {
        spinner.addClass("d-none");
        error.addClass("d-none");
        target_body.html( data );
        tooltips.tooltip();
        initAjaxComponents(target);
      },
      error: function() {
        spinner.addClass("d-none");
        error.removeClass("d-none");
      },
    });
}

function modalAjaxInit( parent ) {
    $(".modal[data-url]", parent).on('shown.bs.modal', function( event ) {
        bootstrapComponentAjaxCall( event.currentTarget, $( '.modal-content', event.currentTarget ), true );
    });
    $(".modal[data-url", parent).on('hidden.bs.modal', function( event ){
        $('.modal-fetched-content', event.currentTarget).html("");
    });
}

function collapseAjaxInit( parent ) {
    $(".collapse[data-url]", parent).on('shown.bs.collapse', function( event ) {
        bootstrapComponentAjaxCall( event.target, $( event.target ), false );
    });
}

function initAjaxComponents( parent ) {
    modalAjaxInit( parent );
    collapseAjaxInit( parent );
}

$( document ).ready( function(){
    initAjaxComponents( document );
});