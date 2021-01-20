/*  created by: Jonas Kiefer
    created on: 20.01.2021
    contact: jonas.kiefer@live.com

    This javascript library implements the logic to add/remove forms to/from a formset in the frontend.
    The needed workflow is described by django it self on the site below in version v.3.1:
    https://docs.djangoproject.com/en/3.1/topics/forms/formsets/#understanding-the-managementform
*/

function updateTotalForms( formPrefix, isIncrement = true ) {
    /*  This is the helper function to increment/decrement the ``{{ form.prefix }}-TOTAL_FORMS´´ field.*/
    const totalFormsInput = document.querySelector('#id_' + formPrefix + '-TOTAL_FORMS');

    var value = parseInt(totalFormsInput.value, 10);
    value = isNaN(value) ? 0 : value;
    if ( isIncrement ){
        value++;
    } else {
        value--;
    }
    totalFormsInput.value = value;
}


function createForm( elementToBeClone, formPrefix, initialCountInput) {
    /*  Steps we need to to on creation:
        - clone the last form
        - reset all initial values.
        - reset id's and names based on the initialCountInput which hold's the count of all forms
        - increment the input with the name ``{{ form.prefix }}-TOTAL_FORMS´´ by 1.
    */

    const clone = elementToBeClone.cloneNode(true);
    if (clone.classList.contains('d-none')){
        clone.classList.remove('d-none');
    }

    // increment initialCountInput value
    initialCountInput.value++;

    var name_regex = new RegExp('(' + formPrefix + '-\\d+-\\w+)');

    var elementsWithId = clone.querySelectorAll('*[id]');
    // todo: append clone it self to the elementsWithId list

    elementsWithId.forEach((item) => {
        _id = item.id
        item.id = item.id.replace(/[0-9]/g, initialCountInput.value - 1)

        clone.querySelectorAll('*[*]=');

        // find data-targets which points to this item
        // find data-parents which points to this item
        // find aria-labelledby which points to this item

        console.log("old_id: " + _id);
        console.log("new_id: " + item.id);
    });



    //elementToBeClone.append( clone );
    //updateTotalForms( formPrefix )
}


function deleteForm( elementToBeDelete, formPrefix, formCount ) {
    /*  Steps we need to to on deletion:
        - change visibility of the form to invisible.
        - decrement the input with the name ``{{ form.prefix }}-TOTAL_FORMS´´ by 1.
        - append input with name ``form-#-DELETE´´ while ``#´´ is representing the number
            of the form which should be deleted.
    */
    elementToBeDelete.classList.add( "d-none" );
    updateTotalForms( formPrefix, false );
    var deleteInput = document.createElement('input');
    deleteInput.setAttribute('name', 'form-' + formCount + '-DELETE' );
    deleteInput.setAttribute('type', 'hidden');
    elementToBeDelete.appendChild( deleteInput );
}


$(document).on('click', '.create-form', function( event ){
    /*  API description:
        - This click event listener is mapped on the class ``create-form``
        - The target element has to implement the ``data-target´´ attribute,
            which tells us which is the target we can clone from.
        - The target element has to implement the ``data-formprefix´´ attribute,
            which tells us which is the prefix of the form.
        - The html template has to implement input field with id
            ``id_{{ wizard.form.management_form.prefix }}_INITIAL_COUNT´´ to tell us what was the initial count of forms
    */
    const submitter = event.target;
    const elementToBeCloneId = submitter.dataset.target;   // the target element we can clone from
    const elementToBeClone = document.querySelector(elementToBeCloneId);
    const formPrefix = submitter.dataset.formprefix;
    const initialCountInput = document.querySelector('#id_' + formPrefix + '_INITIAL_COUNT');

    createForm( elementToBeClone, formPrefix, initialCountInput );
});


$(document).on('click', '.delete-form', function( event ){
    /*  API description:
        - This click event listener is mapped on the class ``delete-form´´.
        - The target element has to implement the ``data-target´´ attribute,
            which tells us which the root element for deletion is.
        - The target element has to implement the ``data-formprefix´´ attribute,
            which tells us which is the prefix of the form.
        - The target element has to implement the ``data-formcount´´ attribute,
            which tells us which is the count of the form which shall be deleted.
    */

    const submitter = event.target; // the button which fires the click event for example
    const rootElementId = submitter.dataset.target;   // the target root element id which will be deleted
    const rootElement =  document.querySelector(rootElementId);    // the target root element
    const formPrefix = submitter.dataset.formprefix;
    const formCount = submitter.dataset.formcount;

    deleteForm( rootElement, formPrefix, formCount);
});
