package policy

import rego.v1

# Regras de RBAC
default allow := false

# Usuários na role 4 têm acesso total
allow if {
    some emp in data.employees
    emp.full_name == input.full_name
    4 in emp.roles
}

# Negar acesso se nenhuma das condições acima for verdadeira
deny if {
    not allow
}
