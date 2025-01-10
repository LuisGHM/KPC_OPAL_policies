package policies

default allow = false

# Regra para verificar se o usuário é admin
is_admin {
    input.user.is_superuser == true
}

# Regra para verificar se o usuário é staff
is_staff {
    input.user.is_staff == true
    input.user.is_superuser == false
}

# Permitir admins fazerem tudo
allow {
    is_admin
}

# Permitir staff apenas ler
allow {
    is_staff
    input.action == "read"
}

# Negar outras ações
deny {
    not allow
}
