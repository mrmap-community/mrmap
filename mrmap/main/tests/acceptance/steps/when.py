from behave import when

# Using Django's testing client
@when(u'I visit "{url}"')
def visit(context, url):
    # save response in context for next step
    context.response = context.test.client.get(url)