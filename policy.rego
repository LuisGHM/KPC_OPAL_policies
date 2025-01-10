package app.rbac

# Regra padrão: acesso negado
default allow = false

# Debugging: visualizar os usuários categorizados
debug_admin = {employee.full_name |
    some employee
    employee = data.employees.result[_]
    employee.is_superuser == true
}

debug_staff = {employee.full_name |
    some employee
    employee = data.employees.result[_]
    employee.is_staff == true
    employee.is_superuser == false
}

# Regras de autorização
allow {
    input.user == debug_admin[_]  # Administradores têm acesso total
}

allow {
    input.user == debug_staff[_]  # Funcionários têm acesso limitado
    input.action == "read"        # Apenas ações de leitura
}
