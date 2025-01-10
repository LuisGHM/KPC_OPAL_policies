package policy

default allow = false

# Regras para ações
allow {
    input.method == "GET"  # Leitura é permitida para todos os usuários
    user_is_admin_or_staff
}

allow {
    user_is_admin  # Administradores podem realizar todas as ações
}

# Condição para verificar se o usuário é administrador
user_is_admin {
    user := input.user
    user.is_superuser == true
}

# Condição para verificar se o usuário é staff
user_is_staff {
    user := input.user
    user.is_staff == true
}

# Condição para verificar se o usuário é admin ou staff
user_is_admin_or_staff {
    user_is_admin
}

user_is_admin_or_staff {
    user_is_staff
}
