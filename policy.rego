package app.rbac

# Regra padrão: nega acesso
default allow = false

# Regra para permitir acesso
allow {
    some role
    input.user in roles[role].users
    input.action in roles[role].actions
    input.object in roles[role].objects
}

# Definição das funções (roles) dinâmicas com base nos dados sincronizados
roles = {
    "admin": {
        "users": [u | data.employees[_].is_superuser == true; u = data.employees[_].full_name],
        "actions": ["create", "read", "update", "delete"],
        "objects": ["*"]
    },
    "employee": {
        "users": [u | data.employees[_].is_staff == true; u = data.employees[_].full_name],
        "actions": ["read"],
        "objects": ["finance"]
    }
}
