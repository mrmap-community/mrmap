"""The pair rules of the accounts models, which #1483 re-declared.

Both rules are as old as the models and were declared with Django's
``unique_together``, an option deprecated since Django 5.1 which a later major
takes away. Both are ``UniqueConstraint`` declarations now, and the conversion
changed no rule - which is what the two test classes below tell apart:

* ``PublishRequest`` - one request per pair of organizations. The rule IS an
  index of the table, whose name the constraint carries since
  ``accounts/migrations/0011_the_publish_request_pair_names_its_constraint.py``;
* ``Contact`` - the whole contact block identifies one organization. The
  declaration stands on the abstract, and Django reads the options of a model
  from ONE Meta: the model's own when it declares one, else the first base
  which has one (``extras/models.py`` spells the trap out for the guardian
  bases). ``Organization`` declares a Meta of its own, so the rule of the
  abstract it comes with reaches neither ``accounts_organization`` nor
  ``full_clean`` - it reached neither as ``unique_together`` either.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models.groups import Contact, Organization, PublishRequest

#: the columns of the contact block, in the order the abstract lists them
CONTACT_BLOCK = ('person_name', 'email', 'phone', 'facsimile', 'city',
                 'postal_code', 'address_type', 'address',
                 'state_or_province', 'country')


class PublishRequestPairTests(TestCase):
    """One request per pair of organizations, index included."""

    def setUp(self):
        self.requesting = Organization.objects.create(
            name='Requesting publishing organization')
        self.requested = Organization.objects.create(
            name='Requested publishing organization')

    def test_the_same_pair_holds_one_request(self):
        """The second request of one pair is refused by the table.

        The refusal belongs in the database: two curators of one organization
        asking at the same moment would otherwise both have their request
        standing, and the acceptance of one would grant what the other one
        already granted.
        """
        PublishRequest.objects.create(
            from_organization=self.requesting, to_organization=self.requested)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PublishRequest.objects.create(
                    from_organization=self.requesting,
                    to_organization=self.requested)

    def test_the_other_direction_of_a_pair_is_another_request(self):
        """Asking and being asked are two rules, not one pair of rows.

        The constraint compares the two columns, so ``A`` asking ``B`` and
        ``B`` asking ``A`` are two rows - which is what the acceptance of one
        of them has to leave alone: it grants the direction it states.
        """
        PublishRequest.objects.create(
            from_organization=self.requesting, to_organization=self.requested)
        asking_back = PublishRequest.objects.create(
            from_organization=self.requested,
            to_organization=self.requesting)

        self.assertEqual(PublishRequest.objects.count(), 2)
        self.assertIsNotNone(asking_back.pk)


class OrganizationContactIdentityTests(TestCase):
    """What the rule of the abstract answers for ``Organization``."""

    def test_a_repeated_contact_block_refuses_nothing(self):
        """Re-declaring the option did not add a rule to the model.

        Two organizations which answer the same ten contact columns are the
        same contact on paper, and nothing refuses the second one - neither a
        validation of the row nor an index of the table. That asymmetry is the
        shape the rule had before #1483 and had to keep: an index over the
        block of ``accounts_organization`` is a schema change of its own, with
        a dedupe of the rows a deployment already carries, and this issue
        converts declarations instead of tightening rules.
        """
        Organization.objects.create(
            name='Organization of the first contact',
            person_name='Ada Lovelace', email='ada@example.com')
        twin = Organization(
            name='Organization of the repeated contact',
            person_name='Ada Lovelace', email='ada@example.com')

        twin.full_clean()
        twin.save()

        self.assertEqual(Organization.objects.count(), 2)

    def test_the_abstract_declares_the_rule_the_model_does_not_carry(self):
        """Where the declaration stands, and why no migration follows it.

        The two halves are the answer to the question a reader of the pull
        request asks: ``accounts/migrations/0011_...`` renames the index of
        ``accounts_publishrequest`` and brings nothing for the contact block,
        because the block is not an option of ``Organization``. The second
        half is what turns red if a child ever does name it: the row above
        this one shows that the table then has to be deduped first.
        """
        self.assertEqual(
            [sorted(constraint.fields) for constraint in Contact._meta.constraints],
            [sorted(CONTACT_BLOCK)],
            'the abstract no longer declares the block #1483 only re-named')

        self.assertEqual(
            [constraint.name for constraint in Organization._meta.constraints
             if set(CONTACT_BLOCK).issubset(constraint.fields)],
            [],
            'Organization carries the block of its abstract, which is a schema '
            'change and not the conversion #1483 is')
