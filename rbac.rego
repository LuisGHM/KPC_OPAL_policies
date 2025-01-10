package app.rbac

# Por padrão, negar acesso
default allow = false

# Permitir se for superuser
allow {
    some user
    user := input.user
    is_superuser(user)
}

# Permitir leitura para staff
allow {
    some user
    user := input.user
    is_staff(user)
    input.action == "read"
}

# Funções auxiliares para verificar permissões
is_superuser(user) {
    data.result[_].full_name == user
    data.result[_].is_superuser == true
}

is_staff(user) {
    data.result[_].full_name == user
    data.result[_].is_staff == true
}
