#How to Contributing
When contributing to this repository, please first discuss the change you wish to make via issue, email, or any other method with the owners of this repository before making a change.

## Git Workflow
Please follow the following steps on working in our Git:

1. Create an issue
    * Explain your problem precisely. Please use an issue style like [this](https://git.osgeo.org/gitea/hollsandre/MapSkinner/issues/45)
2. Tag the issue correctly (Discussion, Bug, Improvement, New Feature, ...)
3. Assigne the correct person. If you are not sure who would be the correct one, just assigne someone. They will know if they can do it or delegate it further
4. If your are responsible for the issue, create an own branch per issue. This workflow is nicely done in Gitlab, but Github does not support the automatic creation of a branch from an issue. However, if your issue has the name `#42 Great Issue`, please use the following as branch name `42_Great_Issue`. 
5. **Always** fork the issue branch from the depending milestone branch your developing for. (See the [tags](https://git.osgeo.org/gitea/hollsandre/MapSkinner/releases))The master branch will only be pulled, if we want to get a current "milestone" status.
6. Work on the branch
7. Use a good commit style as following described.
8. When the work is done, create a Pull-Request and explain what you did. **Please note**: Always set the Pull-Request relation to **milestone --- your_branch**
9. Close your issue, leave a commented link to the Pull-Request

##Issue Style
Please use `markdown` for styling your issue. Always explain **what currently exists**, like how the bug can be triggered, followed by a **"wish" or suggestion** what **should** happen on this specific problem. Take a look on older Issues to get an idea:
* [#44](https://git.osgeo.org/gitea/hollsandre/MapSkinner/issues/44)
* [#45](https://git.osgeo.org/gitea/hollsandre/MapSkinner/issues/45)
* [#36](https://git.osgeo.org/gitea/hollsandre/MapSkinner/issues/36)

##Commit Style
Commits are a great thing to rethink your last actions again and are useful for code review. So please follow the following style to improve the quality of your commits:

```shell
Title goes here

issue #123
* fixes a bug where A did B but C was expected
  *  refactors class_TRE and class_DFR 
  *  adds new helper class 
* adds new templates
* adds new constants in app1/settings.py

```

As you can see the commit is written in a self-explanatory manner, which means, we do not write what **we** did, but what **the commit changes**. 

##Pull Request Process
1. Ensure any install or build dependencies are removed before the end of the layer when doing a build.
1. Update the README.md with details of changes to the interface, this includes new environment variables, exposed ports, useful file locations and container parameters.
1. Increase the version numbers in any examples files and the README.md to the new version that this Pull Request would represent. The versioning scheme we use is SemVer.
1. You may merge the Pull Request in once you have the sign-off of two other developers, or if you do not have permission to do that, you may request the second reviewer to merge it for you.


## Coding Style
We take the [PEP 8](https://www.python.org/dev/peps/pep-0008/#introduction) coding style as reference for our project. Since PyCharm, which we use, supports PEP 8, it is pretty simple to follow the guidelines. 

Never forget: Your code is art, you are an artist. Behave accordingly.

## Quality assurance
### Sonarqube
We use a [Sonarqube](https://www.sonarqube.org/) [Server](#) to analyse our code about quality, security vulnerability, testcoverage and testresults.

If your changes doesnt pass the quality gate, your branch will not be merged! 

### Install SonarLint
In Pycharm press
```shell
ctrl + alt + s
```
to open the Settings. Go to `Plugins` and search `SonarLint`. Now you can install the plugin.

### Usage
Before you commit something, you should always take a look to your SonarLint report in your development environment. SonarLint will show you the mistakes that you do and which are restricted by our Sonarqube server rules.

## Documentation
Since we create the code documentation automatically from the sources, we use the spinx system and therefore their [Google Style](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html). 

```python

    def function_xy(self, identifier: str = None):
        """ Restore the metadata of a wfs service

        Args:
            identifier (str): Identifies which layer should be restored.
        Returns:
             nothing
        """
```

### Quick explanation
1. First line is used as title for the documentation
   * keep ist small and simple
1. Second line is empty - always!
2. From the third line on, you may explain in detail what is going on in your function. Do not overuse this
3. After the explanation, keep another line empty
4. `Args:` defines the arguments
  * please use type hinting using e.g. `(str)` whenever you can
5. `Returns:` defines what can be expected as a return value when the function is used
  * when the function does not return anything, because it is e.g. an object method that changes the object itself, simply type `nothing`


### Comments
There are functions which are more complex than other. Nevertheless imagine you are explaining your code to a newbie programmer, who just started working in your organization a couple of days ago and has no idea what the hell is going on. Yes, we know you are an expert programmer, a true hero of coding experience and of course: 
> A tRuE KlInGoN wARriOr dOEs NOt cOmMenT hIs COdE!

**but** please do not forget: This is an open source project and for the sake of the community and those who want to be experts like you, one day: Please comment!

Please try not only to explain what you are doing (which is obvious in most cases), but also **why** you are doing it this way. Is it a preparation for later post-processing? Is it a nice hack, you found on stackoverflow (in this case, please paste the uri as well), and so on.

### Example
```python


@check_permission(Permission(can_update_service=True))
@transaction.atomic
def update_service(request: HttpRequest, id: int):
    """ Compare old service with new service and collect differences

    Args:
        request: The incoming request
        user: The active user
        id: The service id
    Returns:
        A rendered view
    """
    user = user_helper.get_user(request)

    template = "service_differences.html"
    update_params = request.session["update"]
    url_dict = service_helper.split_service_uri(update_params["full_uri"])
    new_service_type = url_dict.get("service")
    old_service = Service.objects.get(id=id)

    # check if metadata should be kept
    keep_custom_metadata = request.POST.get("keep-metadata", None)
    if keep_custom_metadata is None:
        keep_custom_metadata = request.session.get("keep-metadata", "")
    request.session["keep-metadata"] = keep_custom_metadata
    keep_custom_metadata = keep_custom_metadata == "on"


    # get info which layers/featuretypes are linked (old->new)
    links = json.loads(request.POST.get("storage", '{}'))
    update_confirmed = utils.resolve_boolean_attribute_val(request.POST.get("confirmed", 'false'))

    # parse new capabilities into db model
    registrating_group = old_service.created_by
    new_service = service_helper.get_service_model_instance(service_type=url_dict.get("service"), version=url_dict.get("version"), base_uri=url_dict.get("base_uri"), user=user, register_group=registrating_group)
    xml = new_service["raw_data"].service_capabilities_xml
    new_service = new_service["service"]

    # Collect differences
    comparator = ServiceComparator(service_1=new_service, service_2=old_service)
    diff = comparator.compare_services()

    if update_confirmed:
        # check cross service update attempt
        if old_service.servicetype.name != new_service_type.value:
            # cross update attempt -> forbidden!
            messages.add_message(request, messages.ERROR, SERVICE_UPDATE_WRONG_TYPE)
            return BackendAjaxResponse(html="", redirect="{}/service/detail/{}".format(ROOT_URL, str(old_service.metadata.id))).get_response()

        if not keep_custom_metadata:
            # the update is confirmed, we can continue changing the service!
            # first update the metadata of the whole service
            md = update_helper.update_metadata(old_service.metadata, new_service.metadata)
            old_service.metadata = md
            # don't forget the timestamp when we updated the last time
            old_service.metadata.last_modified = timezone.now()
            # save the metadata changes
            old_service.metadata.save()
        # secondly update the service itself, overwrite the metadata with the previously updated metadata
        old_service = update_helper.update_service(old_service, new_service)
        old_service.last_modified = timezone.now()

        if new_service.servicetype.name == ServiceTypes.WFS.value:
            old_service = update_helper.update_wfs_elements(old_service, new_service, diff, links, keep_custom_metadata)

        elif new_service.servicetype.name == ServiceTypes.WMS.value:
            old_service = update_helper.update_wms_elements(old_service, new_service, diff, links, keep_custom_metadata)

        cap_document = CapabilityDocument.objects.get(related_metadata=old_service.metadata)
        cap_document.current_capability_document = xml
        cap_document.save()

        old_service.save()
        del request.session["keep-metadata"]
        del request.session["update"]
        user_helper.create_group_activity(old_service.metadata.created_by, user, SERVICE_UPDATED, old_service.metadata.title)
        return BackendAjaxResponse(html="", redirect="{}/service/detail/{}".format(ROOT_URL,str(old_service.metadata.id))).get_response()
    else:
        # otherwise
        params = {
            "diff": diff,
            "old_service": old_service,
            "new_service": new_service,
            "page_indicator_list": [False, True],
        }
        #request.session["update_confirmed"] = True
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())


```
