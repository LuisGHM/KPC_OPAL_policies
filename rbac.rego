package policy

# Padrão: negar acesso
default allow := false

# Usuários com role 4 têm acesso
allow if {
    some emp in data.employees
    emp.full_name == input.full_name
    4 in emp.roles  # Verifica se o usuário tem a role 4
}
