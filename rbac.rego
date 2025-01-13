package policy

import rego.v1

# Regras de RBAC
default allow := false

# Superusuários têm acesso total
allow if {
	some emp in data.employees
	emp.full_name == input.full_name
	emp.is_superuser == true
}

# Usuários staff podem realizar ações específicas (e.g., "read")
allow if {
	some emp in data.employees
	emp.full_name == input.full_name
	emp.is_staff == true
	some action in input.allowed_actions
	action == "read"
}

# Negar acesso se nenhuma das condições acima for verdadeira
deny if {
	not allow
}
