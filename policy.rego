package app.rbac

# Regra padrão: acesso negado
default allow = false

# Regra de autorização
allow {
    input.user == "admin"  # Verifica se o usuário é administrador
    input.action != ""     # Administradores podem executar qualquer ação
}

allow {
    input.user == staff_users[_]  # Verifica se o usuário está na lista de funcionários
    input.action == "read"        # Funcionários só podem realizar ações de leitura
}

# Dados dinâmicos de roles a partir da API OPAL
staff_users = {user |
    some employee
    employee = data.employees.result[_]
    employee.is_staff == true
    employee.is_superuser == false  # Garante que não são superusuários
    user = employee.full_name
}

admin_users = {user |
    some employee
    employee = data.employees.result[_]
    employee.is_superuser == true
    user = employee.full_name
}
