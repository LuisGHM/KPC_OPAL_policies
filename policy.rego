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

# Informação de depuração
debug_info = {
    "input_user": input.user,
    "input_action": input.action,
    "admin_users": debug_admin,
    "staff_users": debug_staff
}

# Regras de autorização
allow {
    some employee
    employee = data.employees.result[_]
    employee.full_name == input.user
    employee.is_superuser == true
}

allow {
    some employee
    employee = data.employees.result[_]
    employee.full_name == input.user
    employee.is_staff == true
    employee.is_superuser == false
    input.action == "read"
}
