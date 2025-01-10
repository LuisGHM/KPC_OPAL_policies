package app.rbac

# Permitir se for superuser
allow {
    input.user.is_superuser == true
}

# Permitir leitura para staff
allow {
    input.user.is_staff == true
    input.action == "read"
}

# Negar outras ações
allow {
    false
}
