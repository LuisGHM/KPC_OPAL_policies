package app.rbac

# Por padrão, negar acesso
default allow = false

# Permitir se for superuser
allow {
    some user_super
    user_super_role := input.user
    is_superuser(user_super)
}

# Permitir leitura para staff
allow {
    some user_staff
    user_staff_role := input.user
    is_staff(user_staff)
    input.action == "read"
}

# Funções auxiliares para verificar permissões
is_superuser(user_super) {
    data.result[_].full_name == user_super
    data.result[_].is_superuser == true
}

is_staff(user_staff) {
    data.result[_].full_name == user_staff
    data.result[_].is_staff == true
}
