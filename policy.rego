package app.rbac

# Regra padrão: acesso negado
default allow = false

# Debugging: visualize os usuários extraídos
debug_staff = {user |
    some employee
    employee = data.employees.result[_]
    employee.is_staff == true
    employee.is_superuser == false
    user = employee.full_name
}

debug_admin = {user |
    some employee
    employee = data.employees.result[_]
    employee.is_superuser == true
    user = employee.full_name
}

# Regra de autorização
allow {
    input.user == "admin"  # Acesso completo para administradores fixos (testar bypass)
}

allow {
    input.user == debug_staff[_]  # Funcionários
    input.action == "read"
}

allow {
    input.user == debug_admin[_]  # Administradores
}
