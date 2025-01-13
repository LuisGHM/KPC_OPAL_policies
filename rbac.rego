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
}

allow if {
	some employee
	employee := data.employees[_]
	employee.full_name == input.full_name
	employee.is_staff == true
	some action
	input.allowed_actions[action] == "read"
}

# Bloqueia se não atender às condições acima
deny if {
	not allow
}
