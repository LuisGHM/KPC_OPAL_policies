package app.rbac

# Regra padrão: acesso negado
default allow = false

# Regra de autorização
allow {
    some role
    input.user == roles[role].users[_]  # Verifica se o usuário pertence à lista
    input.action == roles[role].actions[_]  # Verifica se a ação é permitida
    input.object == roles[role].objects[_]  # Verifica se o objeto é permitido
}

# Definição de funções
roles = {
    "admin": {
        "users": ["alice"],
        "actions": ["create", "read", "update", "delete"],
        "objects": ["*"]
    },
    "employee": {
        "users": ["bob"],
        "actions": ["read"],
        "objects": ["finance"]
    }
}
