package policy

# Regras de RBAC baseadas em roles
default allow := false

# Usuários com role 4 têm acesso total
allow if {
    some emp in data.employees
    emp.full_name == input.full_name
    4 in emp.roles  # Verifica se o usuário tem a role 4
}

# Negar acesso se nenhuma das condições acima for verdadeira
deny if {
    not allow
}
