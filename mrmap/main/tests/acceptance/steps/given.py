from behave import given

# Using Django's testing client
@given(u'User "{user}" is logged in')
def user_login(context, url):
    # save response in context for next step
    context.response = context.test.client.get(url)