.. _usecases-constraints:


=============
Constraints
=============

Constraint: ein Nutzer kann in mehreren Organisationen sein.
Begründung: Ermöglicht die Konfiguration von eingeschränkten Zugriffen auf eine Teilmenge von Resourcen einer Organisation
Nachteil: Führt zu viel Administrationsaufwand wenn z.B. Nutzer A auf Resource Y & X Zugriff haben soll und Nutzer B auf Resource X & Z --> Resourcen müssten in einzelnen Organisationen

Constraint: eine Organisation kann mehrere Unterorganisationen haben.
Begründung:

Constraint: eine Resource gehört genau einer Organisation.
Begründung:

Constraint: Resourcen im Besitz einer Unterorganisation können von jeder übergeordneten Organisation administriert werden.
Begründung: use case --> Nutzer soll eingeschrenkt Zugriff auf Teilmenge von Resourcen seiner Organisation erhalten. Workflow: Owner der Resource an die untergeordnete Organisation übertragen.



Rolle:

- Name
- Members
- Permissions
- Objects


Brauchen wir dann noch Unterorganisationen?

Brauchen wir den Published for request workflow?