package policy

import rego.v1

# Regras de RBAC baseadas em roles
default allow := false

# Usuários com role 4 (admin) têm acesso total
allow if {
    some emp in data.employees
    emp.full_name == input.full_name
    some role in emp.roles  # Verifica se o usuário possui a role 4
    role == 4
}

# Negar acesso se nenhuma das condições acima for verdadeira
deny if {
    not allow
}