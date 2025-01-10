package employees

default allow = false

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

# Bloqueia qualquer outra ação para `is_staff`
deny {
    input.is_staff == true
    not allow
}
