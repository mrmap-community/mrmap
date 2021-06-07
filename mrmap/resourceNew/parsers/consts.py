NS_WC = "*[local-name()='"  # Namespace wildcard

IF_THEN_ELSE = f"concat(substring(%(val_1)s, 1, number(%(condition)s) * string-length(%(val_1)s)), substring(%(val_2)s, 1, number(not(%(condition)s)) * string-length(%(val_2)s)))"
