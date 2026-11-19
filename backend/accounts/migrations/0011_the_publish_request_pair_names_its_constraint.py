# `PublishRequest` declares its one-pending-request-per-organization-pair rule
# as a `UniqueConstraint` now instead of the deprecated `unique_together`
# (#1483). The rule, the columns and the index stay; only the name the
# constraint carries is its own now instead of the hash `unique_together`
# derived from the table and the columns. So the operation states the new
# constraint and renames the existing one - and with it its backing index -
# instead of dropping and rebuilding it.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0010_organizationgroupobjectpermission_created_at_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterUniqueTogether(
                    name='publishrequest',
                    unique_together=set()),
                migrations.AddConstraint(
                    model_name='publishrequest',
                    constraint=models.UniqueConstraint(
                        fields=('from_organization', 'to_organization'),
                        name='unique_publish_request_per_organization_pair'),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE "accounts_publishrequest" RENAME CONSTRAINT'
                        ' "accounts_publishrequest_from_organization_id_to__f7ac9bcc_uniq"'
                        ' TO "unique_publish_request_per_organization_pair"'),
                    reverse_sql=(
                        'ALTER TABLE "accounts_publishrequest" RENAME CONSTRAINT'
                        ' "unique_publish_request_per_organization_pair"'
                        ' TO "accounts_publishrequest_from_organization_id_to__f7ac9bcc_uniq"'),
                ),
            ],
        ),
    ]
