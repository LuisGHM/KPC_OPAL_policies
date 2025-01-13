package policy

import future.keywords.if

# Regras de RBAC
default allow = false

# Verifica se a pessoa tem permissão
allow if {
    some employee
    # Encontra o registro do funcionário com o mesmo nome
    employee := data.employees[_]
    employee.full_name == input.full_name
    # Verifica as permissões
    employee.is_superuser == true
    or
    (employee.is_staff == true and input.allowed_actions[_] == "read")
}

# Bloqueia se não atender às condições acima
deny if {
    not allow
}
