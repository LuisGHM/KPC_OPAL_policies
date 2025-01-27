package policy

# Padrão: negar acesso
default allow := false

# Usuários com role 4 têm acesso
allow if {
    some emp
    emp := data.employees[_]  # Itera pelos elementos da lista
    emp.full_name == input.full_name
    some r
    r := emp.roles[_]  # Itera pelos elementos da lista roles
    r == 4
}
