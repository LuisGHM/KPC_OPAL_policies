package employees

import future.keywords.in

# Regras principais
default allow = false
default deny = false

# Permite tudo para superusuários
allow {
    input.is_superuser == true
}

# Define restrições para `is_staff`
allow {
    input.is_staff == true
    some action in input.allowed_actions
    action == "read"  # Exemplo de ação permitida
}

# Define negação explícita para casos não permitidos
deny {
    input.is_staff == true
    not allow
}
