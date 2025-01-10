package app.rbac

# Por padrão, negar acesso
default allow = false

# Permitir se for superuser
allow {
    some u
    u := input.user
    is_superuser(u)
}

# Permitir leitura para staff
allow {
    some u
    u := input.user
    is_staff(u)
    input.action == "read"
}

# Funções auxiliares para verificar permissões
is_superuser(u) {
    data.result[_].full_name == u
    data.result[_].is_superuser == true
}

is_staff(u) {
    data.result[_].full_name == u
    data.result[_].is_staff == true
}
